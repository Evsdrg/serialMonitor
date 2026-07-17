"""测试 pySerial RFC2217 传输处理器。"""

import socket
import threading
import time
from unittest.mock import Mock

import pytest
import serial
import serial.rfc2217

from core.rfc2217_handler import Rfc2217Handler
from core.transport import TransportOperation


class _Rfc2217Redirector:
    def __init__(self, serial_port, connection):
        self.serial = serial_port
        self.connection = connection
        self._write_lock = threading.Lock()
        self.manager = serial.rfc2217.PortManager(self.serial, self)
        self.running = True
        self.received = bytearray()
        self._reader = threading.Thread(target=self._serial_to_socket, daemon=True)
        self._poller = threading.Thread(target=self._poll_modem, daemon=True)

    def write(self, data):
        with self._write_lock:
            self.connection.sendall(data)

    def _serial_to_socket(self):
        try:
            while self.running:
                data = self.serial.read(self.serial.in_waiting or 1)
                if data:
                    self.write(b"".join(self.manager.escape(data)))
        except (OSError, serial.SerialException):
            pass

    def _poll_modem(self):
        try:
            while self.running:
                self.manager.check_modem_lines()
                time.sleep(0.05)
        except (OSError, serial.SerialException):
            pass

    def run(self):
        self._reader.start()
        self._poller.start()
        try:
            while self.running:
                data = self.connection.recv(1024)
                if not data:
                    break
                payload = b"".join(self.manager.filter(data))
                if payload:
                    self.received.extend(payload)
                    self.serial.write(payload)
        except OSError:
            pass
        finally:
            self.running = False


class _Rfc2217Server:
    def __init__(self):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.serial = serial.serial_for_url("loop://", timeout=0.05)
        self.connection = None
        self.redirector = None
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            self.connection, _address = self.listener.accept()
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.redirector = _Rfc2217Redirector(self.serial, self.connection)
            self.redirector.run()
        except OSError:
            pass

    def close(self):
        if self.connection is not None:
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
        self.listener.close()
        self.serial.close()
        self.thread.join(timeout=2)


class _SilentServer:
    def __init__(self):
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.connection = None
        self.accepted = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            self.connection, _address = self.listener.accept()
            self.accepted.set()
            while self.connection.recv(1024):
                pass
        except OSError:
            pass

    def close(self):
        if self.connection is not None:
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection.close()
        self.listener.close()
        self.thread.join(timeout=2)


@pytest.fixture
def rfc2217_server():
    server = _Rfc2217Server()
    yield server
    server.close()


@pytest.fixture
def rfc_handler():
    handler = Rfc2217Handler()
    yield handler
    handler.shutdown()


class TestRfc2217Handler:
    def test_initial_state(self, rfc_handler):
        assert rfc_handler.is_open() is False
        assert rfc_handler.is_connecting() is False
        assert rfc_handler.current_host is None
        assert rfc_handler.current_port is None
        assert rfc_handler.last_error is None

    def test_build_url_supports_ipv6_and_options(self):
        assert Rfc2217Handler.build_url(
            "2001:db8::1",
            2217,
            network_timeout=1.5,
            ignore_set_control=True,
            poll_modem=True,
        ) == (
            "rfc2217://[2001:db8::1]:2217?"
            "timeout=1.5&ign_set_control&poll_modem"
        )

    def test_open_rejects_invalid_endpoint(self, qtbot, rfc_handler):
        with qtbot.waitSignal(rfc_handler.error_occurred, timeout=1000):
            assert rfc_handler.open("", 70000) is False

        assert rfc_handler.last_error_context == "connect"
        assert rfc_handler.is_connecting() is False

    def test_open_is_non_blocking_and_negotiates(
        self, qtbot, rfc2217_server, rfc_handler
    ):
        started = time.monotonic()

        with qtbot.waitSignal(rfc_handler.connection_changed, timeout=3000) as signal:
            assert rfc_handler.open(
                "127.0.0.1",
                rfc2217_server.port,
                baudrate=115200,
                parity="N",
                databits=8,
                stopbits=1,
                dtr=False,
                rts=False,
                network_timeout=1,
            ) is True
            call_elapsed = time.monotonic() - started

        assert call_elapsed < 0.1
        assert signal.args == [True, f"127.0.0.1:{rfc2217_server.port}"]
        assert rfc_handler.is_open() is True
        assert rfc2217_server.serial.baudrate == 115200
        assert rfc2217_server.serial.dtr is False
        assert rfc2217_server.serial.rts is False

    def test_full_byte_roundtrip_and_control_lines(
        self, qtbot, rfc2217_server, rfc_handler
    ):
        with qtbot.waitSignal(rfc_handler.connection_changed, timeout=3000):
            assert rfc_handler.open(
                "127.0.0.1", rfc2217_server.port, network_timeout=1
            ) is True

        payload = bytes(range(256))
        received = bytearray()
        rfc_handler.data_received.connect(received.extend)
        assert rfc_handler.write_data(payload) is True
        qtbot.waitUntil(lambda: len(received) >= len(payload), timeout=3000)
        assert bytes(received) == payload

        assert rfc_handler.set_dtr(False) is True
        assert rfc_handler.set_rts(False) is True
        qtbot.waitUntil(lambda: rfc2217_server.serial.dtr is False, timeout=2000)
        qtbot.waitUntil(lambda: rfc2217_server.serial.rts is False, timeout=2000)

    def test_non_rfc_server_fails_after_negotiation_timeout(
        self, qtbot, rfc_handler
    ):
        server = _SilentServer()
        changes = []
        rfc_handler.connection_changed.connect(lambda *args: changes.append(args))
        try:
            with qtbot.waitSignal(rfc_handler.error_occurred, timeout=3000):
                assert rfc_handler.open(
                    "127.0.0.1", server.port, network_timeout=0.2
                ) is True

            qtbot.waitUntil(lambda: not rfc_handler.is_connecting(), timeout=3000)
            assert rfc_handler.is_open() is False
            assert rfc_handler.last_error_context == "connect"
            assert changes == [(False, f"127.0.0.1:{server.port}")]
        finally:
            server.close()

    def test_close_request_does_not_block_gui(
        self, qtbot, rfc2217_server, rfc_handler
    ):
        with qtbot.waitSignal(rfc_handler.connection_changed, timeout=3000):
            rfc_handler.open(
                "127.0.0.1", rfc2217_server.port, network_timeout=1
            )

        with qtbot.waitSignal(rfc_handler.connection_changed, timeout=3000) as signal:
            started = time.monotonic()
            rfc_handler.close()
            call_elapsed = time.monotonic() - started

        assert call_elapsed < 0.1
        assert signal.args == [False, f"127.0.0.1:{rfc2217_server.port}"]
        assert rfc_handler.is_open() is False

    def test_close_flushes_queued_write(
        self, qtbot, rfc_handler, rfc2217_server
    ):
        with qtbot.waitSignal(rfc_handler.connection_changed, timeout=3000):
            assert rfc_handler.open("127.0.0.1", rfc2217_server.port)

        payload = b"final payload\xff"
        with qtbot.waitSignal(rfc_handler.connection_changed, timeout=3000):
            assert rfc_handler.write_data(payload) is True
            rfc_handler.close()

        qtbot.waitUntil(
            lambda: rfc2217_server.redirector is not None
            and bytes(rfc2217_server.redirector.received) == payload,
            timeout=2000,
        )

    def test_shutdown_interrupts_long_negotiation(self, rfc_handler):
        server = _SilentServer()
        try:
            assert rfc_handler.open(
                "127.0.0.1", server.port, network_timeout=30.0
            ) is True
            assert server.accepted.wait(timeout=2)
            time.sleep(0.75)

            started = time.monotonic()
            assert rfc_handler.shutdown(timeout_ms=3000) is True

            assert time.monotonic() - started < 3.0
            assert rfc_handler.state == Rfc2217Handler.DISCONNECTED
        finally:
            server.close()

    def test_close_during_negotiation_is_clean(self, qtbot, rfc_handler):
        server = _SilentServer()
        errors = []
        rfc_handler.error_occurred.connect(errors.append)
        try:
            assert rfc_handler.open(
                "127.0.0.1", server.port, network_timeout=0.3
            ) is True

            with qtbot.waitSignal(
                rfc_handler.connection_changed, timeout=3000
            ) as signal:
                rfc_handler.close()

            assert signal.args == [False, f"127.0.0.1:{server.port}"]
            assert errors == []
            assert rfc_handler.state == Rfc2217Handler.DISCONNECTED
        finally:
            server.close()

    def test_write_rejected_when_disconnected(self, rfc_handler):
        assert rfc_handler.write_data(b"data") is False
        assert rfc_handler.set_dtr(True) is False
        assert rfc_handler.set_rts(True) is False

    def test_full_write_queue_emits_typed_write_error(self, qtbot, rfc_handler):
        worker = Mock()
        worker.enqueue.return_value = False
        rfc_handler._worker = worker
        rfc_handler._state = Rfc2217Handler.CONNECTED

        with qtbot.waitSignal(rfc_handler.transport_error) as blocker:
            assert rfc_handler.write_data(b"data") is False

        assert blocker.args[0].operation is TransportOperation.WRITE

    def test_worker_write_error_keeps_write_operation(self, qtbot, rfc_handler):
        worker = Mock()
        rfc_handler._worker = worker

        with qtbot.waitSignal(rfc_handler.transport_error) as blocker:
            rfc_handler._on_worker_error(worker, "write failed", "write")

        assert blocker.args[0].operation is TransportOperation.WRITE
