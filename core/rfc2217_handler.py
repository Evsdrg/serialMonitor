"""基于 pySerial 3.5 的 RFC2217 传输处理器。"""

from __future__ import annotations

import ipaddress
import logging
import queue
import socket
import threading
import time
from typing import Any, Optional

import serial
import serial.rfc2217
from PyQt6.QtCore import QThread, pyqtSignal

from core.transport import (
    DisconnectReason,
    TransportHandler,
    TransportOperation,
    TransportState,
)

logger = logging.getLogger(__name__)


class _WorkerCommandError(Exception):
    def __init__(self, context: str, cause: Exception) -> None:
        super().__init__(str(cause))
        self.context = context


class _Rfc2217Worker(QThread):
    connected = pyqtSignal(object, str)
    data_received = pyqtSignal(object, bytes)
    error_occurred = pyqtSignal(object, str, str)

    def __init__(
        self,
        *,
        url: str,
        endpoint: str,
        baudrate: int,
        parity: str,
        databits: int,
        stopbits: float,
        dtr: bool,
        rts: bool,
    ) -> None:
        super().__init__()
        self.url = url
        self.endpoint = endpoint
        self.baudrate = baudrate
        self.parity = parity
        self.databits = databits
        self.stopbits = stopbits
        self.dtr = dtr
        self.rts = rts
        self._stop_event = threading.Event()
        self._close_requested = threading.Event()
        self._connected_event = threading.Event()
        self._interrupt_started = threading.Event()
        self._worker_done = threading.Event()
        self._commands: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1024)
        self._remote: Optional[serial.rfc2217.Serial] = None
        self._close_lock = threading.Lock()

    def request_stop(self) -> None:
        self._close_requested.set()
        if not self._connected_event.is_set():
            self._start_interrupt()

    def force_stop(self) -> None:
        self._close_requested.set()
        self._stop_event.set()
        self._start_interrupt()

    def _start_interrupt(self) -> None:
        if self._interrupt_started.is_set():
            return
        self._interrupt_started.set()
        threading.Thread(target=self._interrupt_remote, daemon=True).start()

    def _interrupt_remote(self) -> None:
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline and not self._worker_done.is_set():
            remote = self._remote
            if remote is not None:
                self._release_pyserial_waits(remote)
                remote_socket = getattr(remote, "_socket", None)
                if remote_socket is not None:
                    try:
                        remote_socket.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
            time.sleep(0.01)

    @staticmethod
    def _release_pyserial_waits(remote: serial.rfc2217.Serial) -> None:
        # pySerial 3.5 polls private RFC2217 state while open() negotiates.
        # Releasing it keeps cancellation bounded without copying its protocol.
        for option in getattr(remote, "_telnet_options", None) or ():
            option.state = serial.rfc2217.INACTIVE
            option.active = False
        for option in (getattr(remote, "_rfc2217_options", None) or {}).values():
            option.state = serial.rfc2217.ACTIVE

    def enqueue(self, command: str, value: Any) -> bool:
        if self._stop_event.is_set() or self._close_requested.is_set():
            return False
        try:
            self._commands.put_nowait((command, value))
            return True
        except queue.Full:
            return False

    def run(self) -> None:
        connected = False
        remote: Optional[serial.rfc2217.Serial] = None
        try:
            remote = serial.rfc2217.Serial(
                port=None,
                baudrate=self.baudrate,
                bytesize=self.databits,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=0.05,
                write_timeout=None,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            remote.port = self.url
            remote.dtr = self.dtr
            remote.rts = self.rts
            self._remote = remote
            remote.open()

            if self._stop_event.is_set() or self._close_requested.is_set():
                return

            connected = True
            self._connected_event.set()
            self.connected.emit(self, self.endpoint)

            while not self._stop_event.is_set():
                self._process_commands(remote)
                if self._close_requested.is_set():
                    self._stop_event.set()
                if self._stop_event.is_set():
                    break
                data = remote.read(remote.in_waiting or 1)
                if data:
                    self.data_received.emit(self, data)
        except _WorkerCommandError as e:
            if not self._stop_event.is_set() and not self._close_requested.is_set():
                self.error_occurred.emit(self, str(e), e.context)
        except (OSError, ValueError, serial.SerialException) as e:
            if not self._stop_event.is_set() and not self._close_requested.is_set():
                context = "io" if connected else "connect"
                self.error_occurred.emit(self, str(e), context)
        except Exception as e:
            if not self._stop_event.is_set() and not self._close_requested.is_set():
                logger.exception("Unexpected RFC2217 worker error")
                context = "io" if connected else "connect"
                self.error_occurred.emit(self, str(e), context)
        finally:
            if remote is not None:
                try:
                    with self._close_lock:
                        remote.close()
                except Exception as e:
                    logger.warning("Error closing RFC2217 connection: %s", e)
            self._remote = None
            self._worker_done.set()

    def _process_commands(self, remote: serial.rfc2217.Serial) -> None:
        while True:
            try:
                command, value = self._commands.get_nowait()
            except queue.Empty:
                return

            try:
                if command == "write":
                    remote.write(value)
                elif command == "dtr":
                    remote.dtr = bool(value)
                elif command == "rts":
                    remote.rts = bool(value)
            except Exception as e:
                context = "write" if command == "write" else "control"
                raise _WorkerCommandError(context, e) from e


class Rfc2217Handler(TransportHandler):
    """对 UI 提供非阻塞 RFC2217 client 接口。"""

    DISCONNECTED = TransportState.DISCONNECTED
    CONNECTING = TransportState.CONNECTING
    CONNECTED = TransportState.CONNECTED
    CLOSING = TransportState.CLOSING

    def __init__(self) -> None:
        super().__init__()
        self.current_host: Optional[str] = None
        self.current_port: Optional[int] = None
        self._worker: Optional[_Rfc2217Worker] = None
        self._disconnect_reason: Optional[DisconnectReason] = None
        self._ever_connected = False

    @property
    def endpoint(self) -> str:
        if self.current_host is None or self.current_port is None:
            return ""
        return f"{self.current_host}:{self.current_port}"

    @staticmethod
    def build_url(
        host: str,
        port: int,
        *,
        network_timeout: float = 3.0,
        ignore_set_control: bool = False,
        poll_modem: bool = False,
    ) -> str:
        host = host.strip().removeprefix("[").removesuffix("]")
        try:
            is_ipv6 = ipaddress.ip_address(host).version == 6
        except ValueError:
            is_ipv6 = ":" in host
        authority = f"[{host}]" if is_ipv6 else host.encode("idna").decode("ascii")
        options = [f"timeout={network_timeout:g}"]
        if ignore_set_control:
            options.append("ign_set_control")
        if poll_modem:
            options.append("poll_modem")
        return f"rfc2217://{authority}:{port}?{'&'.join(options)}"

    def open(
        self,
        host: str,
        port: int | str,
        *,
        baudrate: int | str = 115200,
        parity: str = "N",
        databits: int | str = 8,
        stopbits: float | str = 1,
        dtr: bool = True,
        rts: bool = True,
        network_timeout: float = 3.0,
        ignore_set_control: bool = False,
        poll_modem: bool = False,
    ) -> bool:
        if self._state is not TransportState.DISCONNECTED:
            return True

        try:
            host = host.strip()
            socket_port = int(port)
            timeout = float(network_timeout)
            if not host:
                raise ValueError("Host is required")
            if not 1 <= socket_port <= 65535:
                raise ValueError("Port must be between 1 and 65535")
            if timeout <= 0:
                raise ValueError("Network timeout must be greater than zero")
            serial_baudrate = int(baudrate)
            serial_databits = int(databits)
            serial_stopbits = float(stopbits)
            parity_map = {
                "N": serial.PARITY_NONE,
                "None": serial.PARITY_NONE,
                "E": serial.PARITY_EVEN,
                "Even": serial.PARITY_EVEN,
                "O": serial.PARITY_ODD,
                "Odd": serial.PARITY_ODD,
                "M": serial.PARITY_MARK,
                "Mark": serial.PARITY_MARK,
                "S": serial.PARITY_SPACE,
                "Space": serial.PARITY_SPACE,
            }
            serial_parity = parity_map.get(parity, serial.PARITY_NONE)
            url = self.build_url(
                host,
                socket_port,
                network_timeout=timeout,
                ignore_set_control=ignore_set_control,
                poll_modem=poll_modem,
            )
        except (UnicodeError, ValueError) as e:
            self._emit_error(TransportOperation.CONNECT, str(e))
            return False

        self.current_host = host
        self.current_port = socket_port
        self.last_error = None
        self.last_error_context = None
        self._disconnect_reason = None
        self._ever_connected = False
        worker = _Rfc2217Worker(
            url=url,
            endpoint=self.endpoint,
            baudrate=serial_baudrate,
            parity=serial_parity,
            databits=serial_databits,
            stopbits=serial_stopbits,
            dtr=dtr,
            rts=rts,
        )
        worker.connected.connect(self._on_worker_connected)
        worker.data_received.connect(self._on_worker_data)
        worker.error_occurred.connect(self._on_worker_error)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self._transition(TransportState.CONNECTING)
        worker.start()
        return True

    def close(
        self, reason: DisconnectReason = DisconnectReason.USER
    ) -> None:
        worker = self._worker
        if worker is None:
            return
        self._disconnect_reason = reason
        self._transition(TransportState.CLOSING)
        worker.request_stop()

    def shutdown(self, timeout_ms: int = 10000) -> bool:
        worker = self._worker
        if worker is None:
            return True
        self.close(reason=DisconnectReason.SHUTDOWN)
        grace_ms = max(0, timeout_ms - min(timeout_ms, 2000))
        finished = worker.wait(grace_ms)
        if not finished:
            worker.force_stop()
            finished = worker.wait(max(0, timeout_ms - grace_ms))
        if finished:
            self._complete_worker(worker)
        return finished

    def write_data(self, data: bytes) -> bool:
        return self._enqueue("write", data)

    def set_dtr(self, level: bool) -> bool:
        return self._enqueue("dtr", level)

    def set_rts(self, level: bool) -> bool:
        return self._enqueue("rts", level)

    def _enqueue(self, command: str, value: Any) -> bool:
        worker = self._worker
        if self._state != self.CONNECTED or worker is None:
            return False
        if worker.enqueue(command, value):
            return True
        operation = (
            TransportOperation.WRITE
            if command == "write"
            else TransportOperation.CONTROL
        )
        self._emit_error(
            operation,
            "RFC2217 command queue is full",
            reason=DisconnectReason.IO_ERROR,
        )
        return False

    def _on_worker_connected(self, worker: object, endpoint: str) -> None:
        if worker is not self._worker or self._state is TransportState.CLOSING:
            return
        self.last_error = None
        self.last_error_context = None
        self._ever_connected = True
        self._transition(TransportState.CONNECTED)

    def _on_worker_data(self, worker: object, data: bytes) -> None:
        if worker is self._worker and self._state is TransportState.CONNECTED:
            self.data_received.emit(data)

    def _on_worker_error(
        self, worker: object, message: str, context: str
    ) -> None:
        if worker is not self._worker:
            return
        if context == "connect":
            operation = TransportOperation.CONNECT
            self._disconnect_reason = DisconnectReason.CONNECT_FAILED
        elif context == "write":
            operation = TransportOperation.WRITE
            self._disconnect_reason = DisconnectReason.IO_ERROR
        elif context == "control":
            operation = TransportOperation.CONTROL
            self._disconnect_reason = DisconnectReason.IO_ERROR
        else:
            operation = TransportOperation.READ
            self._disconnect_reason = DisconnectReason.IO_ERROR
        self._emit_error(
            operation,
            message,
            reason=self._disconnect_reason,
            legacy_context=context,
        )

    def _on_worker_finished(self) -> None:
        worker = self.sender()
        if isinstance(worker, _Rfc2217Worker):
            self._complete_worker(worker)

    def _complete_worker(self, worker: _Rfc2217Worker) -> None:
        if worker is not self._worker:
            return
        was_active = self._state is not TransportState.DISCONNECTED
        reason = self._disconnect_reason
        if reason is None:
            reason = (
                DisconnectReason.REMOTE
                if self._ever_connected
                else DisconnectReason.CONNECT_FAILED
            )
        self._worker = None
        self._transition(TransportState.DISCONNECTED, reason)
        if was_active:
            self._ever_connected = False
