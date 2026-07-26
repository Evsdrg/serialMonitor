"""测试透明 TCP socket 传输处理器。"""

import socket
import threading
import time
from unittest.mock import Mock

from PyQt6.QtNetwork import QAbstractSocket, QHostAddress, QTcpServer

from core.socket_handler import SocketHandler
from core.transport import DisconnectReason, TransportState


class TestSocketConnectTimeout:
    """P1: 连接必须有超时，否则黑洞地址会永久 CONNECTING"""

    def test_connect_timeout_fails_session(self, qtbot):
        handler = SocketHandler()
        handler._CONNECT_TIMEOUT_MS = 120

        with qtbot.waitSignal(handler.transport_error, timeout=3000) as blocker:
            handler.open("192.0.2.1", 9)

        assert blocker.args[0].reason is DisconnectReason.CONNECT_FAILED
        assert handler.state is TransportState.DISCONNECTED

    def test_successful_connect_cancels_timeout(self, qtbot):
        server = QTcpServer()
        assert server.listen(QHostAddress("127.0.0.1"), 0)
        handler = SocketHandler()

        with qtbot.waitSignal(handler.connection_changed, timeout=3000):
            handler.open("127.0.0.1", server.serverPort())

        assert handler._connect_timer.isActive() is False
        handler.close()
        server.close()


class TestSocketHandler:
    def test_initial_state(self):
        handler = SocketHandler()

        assert handler.is_open() is False
        assert handler.is_connecting() is False
        assert handler.current_host is None
        assert handler.current_port is None
        assert handler.last_error is None
        assert handler.last_error_context is None

    def test_open_rejects_empty_host(self, qtbot):
        handler = SocketHandler()

        with qtbot.waitSignal(handler.error_occurred, timeout=1000):
            result = handler.open("  ", 9000)

        assert result is False
        assert handler.last_error == "Host is required"
        assert handler.is_connecting() is False

    def test_open_rejects_invalid_port(self, qtbot):
        handler = SocketHandler()

        with qtbot.waitSignal(handler.error_occurred, timeout=1000):
            result = handler.open("127.0.0.1", 70000)

        assert result is False
        assert handler.last_error == "Port must be between 1 and 65535"

    def test_connection_failure_is_non_blocking(self, qtbot):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        handler = SocketHandler()
        changes = []
        handler.connection_changed.connect(lambda *args: changes.append(args))

        started = time.monotonic()
        with qtbot.waitSignal(handler.error_occurred, timeout=2000):
            assert handler.open("127.0.0.1", port) is True
            elapsed = time.monotonic() - started

        assert elapsed < 0.2
        qtbot.waitUntil(lambda: not handler.is_connecting(), timeout=2000)
        qtbot.waitUntil(lambda: bool(changes), timeout=2000)
        assert handler.is_open() is False
        assert handler.last_error
        assert handler.last_error_context == "connect"
        assert changes == [(False, f"127.0.0.1:{port}")]
        assert handler._session_active is False

    def test_close_cancels_connecting_session(self, qtbot):
        handler = SocketHandler()
        assert handler.open("192.0.2.1", 65000) is True

        with qtbot.waitSignal(handler.connection_changed, timeout=1000) as signal:
            handler.close()

        assert signal.args == [False, "192.0.2.1:65000"]
        assert handler.is_open() is False
        assert handler.is_connecting() is False

    def test_write_returns_false_when_disconnected(self):
        handler = SocketHandler()
        assert handler.write_data(b"hello") is False

    def test_write_failure_closes_connection(self, qtbot):
        handler = SocketHandler()
        sock = Mock()
        sock.state.return_value = QAbstractSocket.SocketState.ConnectedState
        sock.write.return_value = -1
        sock.errorString.return_value = "broken pipe"
        handler._socket = sock
        handler.current_host = "127.0.0.1"
        handler.current_port = 9000
        handler._session_active = True
        handler._state = TransportState.CONNECTED

        with qtbot.waitSignal(handler.error_occurred, timeout=1000):
            assert handler.write_data(b"hello") is False

        assert handler.last_error == "broken pipe"
        assert handler.last_error_context == "io"
        sock.abort.assert_called_once()


def test_socket_handler_loopback_roundtrip(qtbot):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    server_received = []
    stop_server = threading.Event()

    def serve():
        connection, _address = listener.accept()
        with connection:
            server_received.append(connection.recv(4096))
            connection.sendall(b"pong\x00")
            stop_server.wait(timeout=2)

    server_thread = threading.Thread(target=serve, daemon=True)
    server_thread.start()
    handler = SocketHandler()

    try:
        with qtbot.waitSignal(handler.connection_changed, timeout=2000) as connected:
            assert handler.open("127.0.0.1", port) is True
        assert connected.args == [True, f"127.0.0.1:{port}"]

        with qtbot.waitSignal(handler.data_received, timeout=2000) as received:
            assert handler.write_data(b"ping\xff") is True

        assert received.args == [b"pong\x00"]
        assert server_received == [b"ping\xff"]

        with qtbot.waitSignal(handler.connection_changed, timeout=1000) as closed:
            handler.close()
        assert closed.args == [False, f"127.0.0.1:{port}"]
    finally:
        handler.close()
        stop_server.set()
        server_thread.join(timeout=2)
        listener.close()


def test_socket_handler_reports_remote_disconnect(qtbot):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    close_peer = threading.Event()

    def serve():
        connection, _address = listener.accept()
        close_peer.wait(timeout=2)
        connection.close()

    server_thread = threading.Thread(target=serve, daemon=True)
    server_thread.start()
    handler = SocketHandler()
    errors = []
    handler.error_occurred.connect(errors.append)

    try:
        with qtbot.waitSignal(handler.connection_changed, timeout=2000):
            assert handler.open("127.0.0.1", port) is True

        with qtbot.waitSignal(handler.connection_changed, timeout=2000) as closed:
            close_peer.set()

        assert closed.args == [False, f"127.0.0.1:{port}"]
        assert errors
        assert handler.is_open() is False
    finally:
        handler.close()
        close_peer.set()
        server_thread.join(timeout=2)
        listener.close()


def test_socket_handler_close_flushes_pending_write(qtbot):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    received = bytearray()

    def serve():
        connection, _address = listener.accept()
        with connection:
            while True:
                data = connection.recv(4096)
                if not data:
                    break
                received.extend(data)

    server_thread = threading.Thread(target=serve, daemon=True)
    server_thread.start()
    handler = SocketHandler()

    try:
        with qtbot.waitSignal(handler.connection_changed, timeout=2000):
            assert handler.open("127.0.0.1", port)

        payload = b"final payload\xff"
        with qtbot.waitSignal(handler.connection_changed, timeout=2000):
            assert handler.write_data(payload)
            assert handler.shutdown(timeout_ms=1000)

        server_thread.join(timeout=2)
        assert bytes(received) == payload
    finally:
        handler.close()
        listener.close()
