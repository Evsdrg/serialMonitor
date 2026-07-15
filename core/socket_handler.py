"""透明 TCP socket 通信处理模块。"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QAbstractSocket, QTcpSocket


class SocketHandler(QObject):
    """基于 Qt 事件循环的非阻塞透明 TCP client。"""

    data_received = pyqtSignal(bytes)
    connection_changed = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._socket = QTcpSocket(self)
        self.current_host: Optional[str] = None
        self.current_port: Optional[int] = None
        self.last_error: Optional[str] = None
        self.last_error_context: Optional[str] = None
        self._session_active = False
        self._connected_once = False
        self._manual_close = False

        self._socket.connected.connect(self._on_connected)
        self._socket.readyRead.connect(self._on_ready_read)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.errorOccurred.connect(self._on_error)

    @property
    def endpoint(self) -> str:
        if self.current_host is None or self.current_port is None:
            return ""
        return f"{self.current_host}:{self.current_port}"

    def is_open(self) -> bool:
        return (
            self._socket.state()
            == QAbstractSocket.SocketState.ConnectedState
        )

    def is_connecting(self) -> bool:
        return self._socket.state() in (
            QAbstractSocket.SocketState.HostLookupState,
            QAbstractSocket.SocketState.ConnectingState,
            QAbstractSocket.SocketState.ClosingState,
        )

    def open(self, host: str, port: int | str) -> bool:
        if self.is_open() or self.is_connecting():
            return True

        try:
            host = host.strip()
            if not host:
                raise ValueError("Host is required")
            socket_port = int(port)
            if not 1 <= socket_port <= 65535:
                raise ValueError("Port must be between 1 and 65535")
        except ValueError as e:
            self.last_error = str(e)
            self.last_error_context = "connect"
            self.error_occurred.emit(str(e))
            return False

        self.current_host = host
        self.current_port = socket_port
        self.last_error = None
        self.last_error_context = None
        self._manual_close = False
        self._session_active = True
        self._connected_once = False
        self._socket.connectToHost(host, socket_port)
        return True

    def close(self) -> None:
        if not self._session_active and not self.is_open() and not self.is_connecting():
            return

        self._manual_close = True
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
                self._finish_disconnected()
        else:
            self._socket.abort()
            if self._session_active:
                self._finish_disconnected()

    def shutdown(self, timeout_ms: int = 1000) -> bool:
        self.close()
        if (
            self._socket.state()
            == QAbstractSocket.SocketState.UnconnectedState
        ):
            return True
        finished = self._socket.waitForDisconnected(timeout_ms)
        if not finished:
            self._socket.abort()
            if self._session_active:
                self._finish_disconnected()
        return finished

    def write_data(self, data: bytes) -> bool:
        if not self.is_open():
            return False

        written = self._socket.write(data)
        if written < 0:
            message = self._socket.errorString()
            self.last_error = message
            self.last_error_context = "io"
            self.error_occurred.emit(message)
            self._manual_close = True
            self._socket.abort()
            if self._session_active:
                self._finish_disconnected()
            return False
        self._socket.flush()
        self.last_error = None
        self.last_error_context = None
        return True

    def _on_connected(self) -> None:
        self.last_error = None
        self.last_error_context = None
        self._connected_once = True
        self._socket.setSocketOption(
            QAbstractSocket.SocketOption.LowDelayOption, 1
        )
        self._socket.setSocketOption(
            QAbstractSocket.SocketOption.KeepAliveOption, 1
        )
        self.connection_changed.emit(True, self.endpoint)

    def _on_ready_read(self) -> None:
        data = bytes(self._socket.readAll())
        if data:
            self.data_received.emit(data)

    def _on_error(self, error: QAbstractSocket.SocketError) -> None:
        if self._manual_close:
            return
        message = self._socket.errorString()
        self.last_error = message
        if not self._connected_once:
            self.last_error_context = "connect"
        elif error == QAbstractSocket.SocketError.RemoteHostClosedError:
            self.last_error_context = "remote_closed"
        else:
            self.last_error_context = "io"
        self.error_occurred.emit(message)
        if (
            self._session_active
            and self._socket.state()
            == QAbstractSocket.SocketState.UnconnectedState
        ):
            self._finish_disconnected()

    def _on_disconnected(self) -> None:
        if self._session_active:
            self._finish_disconnected()

    def _finish_disconnected(self) -> None:
        endpoint = self.endpoint
        self._session_active = False
        self._connected_once = False
        self.connection_changed.emit(False, endpoint)
