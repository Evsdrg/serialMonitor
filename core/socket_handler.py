"""透明 TCP socket 通信处理模块。"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtNetwork import QAbstractSocket, QTcpSocket

from core.transport import (
    DisconnectReason,
    TransportHandler,
    TransportOperation,
    TransportState,
)


class SocketHandler(TransportHandler):
    """基于 Qt 事件循环的非阻塞透明 TCP client。"""

    def __init__(self) -> None:
        super().__init__()
        self._socket = QTcpSocket(self)
        self.current_host: Optional[str] = None
        self.current_port: Optional[int] = None
        self._session_active = False
        self._connected_once = False
        self._manual_close = False
        self._disconnect_reason: Optional[DisconnectReason] = None

        self._socket.connected.connect(self._on_connected)
        self._socket.readyRead.connect(self._on_ready_read)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.errorOccurred.connect(self._on_error)

    @property
    def endpoint(self) -> str:
        if self.current_host is None or self.current_port is None:
            return ""
        return f"{self.current_host}:{self.current_port}"

    def open(self, host: str, port: int | str) -> bool:
        if self._state is not TransportState.DISCONNECTED:
            return True

        try:
            host = host.strip()
            if not host:
                raise ValueError("Host is required")
            socket_port = int(port)
            if not 1 <= socket_port <= 65535:
                raise ValueError("Port must be between 1 and 65535")
        except ValueError as e:
            self._emit_error(TransportOperation.CONNECT, str(e))
            return False

        self.current_host = host
        self.current_port = socket_port
        self.last_error = None
        self.last_error_context = None
        self._manual_close = False
        self._disconnect_reason = None
        self._session_active = True
        self._connected_once = False
        self._transition(TransportState.CONNECTING)
        self._socket.connectToHost(host, socket_port)
        return True

    def close(
        self, reason: DisconnectReason = DisconnectReason.USER
    ) -> None:
        if self._state is TransportState.DISCONNECTED:
            return

        self._manual_close = True
        self._disconnect_reason = reason
        self._transition(TransportState.CLOSING)
        state = self._socket.state()
        if state == QAbstractSocket.SocketState.ClosingState:
            return
        if state == QAbstractSocket.SocketState.ConnectedState:
            self._socket.disconnectFromHost()
            if (
                self._session_active
                and self._socket.state()
                == QAbstractSocket.SocketState.UnconnectedState
            ):
                self._finish_disconnected(reason)
        else:
            self._socket.abort()
            if self._session_active:
                self._finish_disconnected(reason)

    def shutdown(self, timeout_ms: int = 1000) -> bool:
        self.close()
        if (
            self._state is TransportState.DISCONNECTED
        ):
            return True
        finished = self._socket.waitForDisconnected(timeout_ms)
        if not finished:
            self._socket.abort()
            if self._session_active:
                self._finish_disconnected(DisconnectReason.SHUTDOWN)
        return finished or self._state is TransportState.DISCONNECTED

    def write_data(self, data: bytes) -> bool:
        if not self.is_open():
            return False

        written = self._socket.write(data)
        if written < 0:
            message = self._socket.errorString()
            self._emit_error(TransportOperation.WRITE, message)
            self._manual_close = True
            self._disconnect_reason = DisconnectReason.IO_ERROR
            self._socket.abort()
            if self._session_active:
                self._finish_disconnected(DisconnectReason.IO_ERROR)
            return False
        self._socket.flush()
        self.last_error = None
        self.last_error_context = None
        return True

    def _on_connected(self) -> None:
        if self._state is TransportState.CLOSING:
            self._socket.disconnectFromHost()
            return
        self.last_error = None
        self.last_error_context = None
        self._connected_once = True
        self._socket.setSocketOption(
            QAbstractSocket.SocketOption.LowDelayOption, 1
        )
        self._socket.setSocketOption(
            QAbstractSocket.SocketOption.KeepAliveOption, 1
        )
        self._transition(TransportState.CONNECTED)

    def _on_ready_read(self) -> None:
        data = bytes(self._socket.readAll())
        if data:
            self.data_received.emit(data)

    def _on_error(self, error: QAbstractSocket.SocketError) -> None:
        if self._manual_close:
            return
        message = self._socket.errorString()
        if not self._connected_once:
            operation = TransportOperation.CONNECT
            context = "connect"
            self._disconnect_reason = DisconnectReason.CONNECT_FAILED
        elif error == QAbstractSocket.SocketError.RemoteHostClosedError:
            operation = TransportOperation.READ
            context = "remote_closed"
            self._disconnect_reason = DisconnectReason.REMOTE
        else:
            operation = TransportOperation.READ
            context = "io"
            self._disconnect_reason = DisconnectReason.IO_ERROR
        self._emit_error(
            operation,
            message,
            reason=self._disconnect_reason,
            legacy_context=context,
        )
        if (
            self._session_active
            and self._socket.state()
            == QAbstractSocket.SocketState.UnconnectedState
        ):
            self._finish_disconnected(self._disconnect_reason)

    def _on_disconnected(self) -> None:
        if self._session_active:
            reason = self._disconnect_reason
            if reason is None:
                reason = (
                    DisconnectReason.REMOTE
                    if self._connected_once
                    else DisconnectReason.CONNECT_FAILED
                )
            self._finish_disconnected(reason)

    def _finish_disconnected(
        self, reason: DisconnectReason | None = None
    ) -> None:
        if self._state is TransportState.DISCONNECTED:
            return
        self._session_active = False
        self._connected_once = False
        self._transition(
            TransportState.DISCONNECTED,
            reason or DisconnectReason.REMOTE,
        )
