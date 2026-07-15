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
from PyQt6.QtCore import QObject, QThread, pyqtSignal

logger = logging.getLogger(__name__)


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

            if command == "write":
                remote.write(value)
            elif command == "dtr":
                remote.dtr = bool(value)
            elif command == "rts":
                remote.rts = bool(value)


class Rfc2217Handler(QObject):
    """对 UI 提供非阻塞 RFC2217 client 接口。"""

    data_received = pyqtSignal(bytes)
    connection_changed = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    state_changed = pyqtSignal(str)

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CLOSING = "closing"

    def __init__(self) -> None:
        super().__init__()
        self.current_host: Optional[str] = None
        self.current_port: Optional[int] = None
        self.last_error: Optional[str] = None
        self.last_error_context: Optional[str] = None
        self._state = self.DISCONNECTED
        self._worker: Optional[_Rfc2217Worker] = None

    @property
    def endpoint(self) -> str:
        if self.current_host is None or self.current_port is None:
            return ""
        return f"{self.current_host}:{self.current_port}"

    @property
    def state(self) -> str:
        return self._state

    def is_open(self) -> bool:
        return self._state == self.CONNECTED

    def is_connecting(self) -> bool:
        return self._state in (self.CONNECTING, self.CLOSING)

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
        if self._state != self.DISCONNECTED:
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
            self.last_error = str(e)
            self.last_error_context = "connect"
            self.error_occurred.emit(str(e))
            return False

        self.current_host = host
        self.current_port = socket_port
        self.last_error = None
        self.last_error_context = None
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
        self._set_state(self.CONNECTING)
        worker.start()
        return True

    def close(self) -> None:
        worker = self._worker
        if worker is None:
            return
        self._set_state(self.CLOSING)
        worker.request_stop()

    def shutdown(self, timeout_ms: int = 10000) -> bool:
        worker = self._worker
        if worker is None:
            return True
        self.close()
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
        self.last_error = "RFC2217 command queue is full"
        self.last_error_context = "io"
        self.error_occurred.emit(self.last_error)
        return False

    def _set_state(self, state: str) -> None:
        if self._state == state:
            return
        self._state = state
        self.state_changed.emit(state)

    def _on_worker_connected(self, worker: object, endpoint: str) -> None:
        if worker is not self._worker or self._state == self.CLOSING:
            return
        self.last_error = None
        self.last_error_context = None
        self._set_state(self.CONNECTED)
        self.connection_changed.emit(True, endpoint)

    def _on_worker_data(self, worker: object, data: bytes) -> None:
        if worker is self._worker and self._state == self.CONNECTED:
            self.data_received.emit(data)

    def _on_worker_error(
        self, worker: object, message: str, context: str
    ) -> None:
        if worker is not self._worker:
            return
        self.last_error = message
        self.last_error_context = context
        self.error_occurred.emit(message)

    def _on_worker_finished(self) -> None:
        worker = self.sender()
        if isinstance(worker, _Rfc2217Worker):
            self._complete_worker(worker)

    def _complete_worker(self, worker: _Rfc2217Worker) -> None:
        if worker is not self._worker:
            return
        endpoint = self.endpoint
        was_active = self._state != self.DISCONNECTED
        self._worker = None
        self._set_state(self.DISCONNECTED)
        if was_active:
            self.connection_changed.emit(False, endpoint)
