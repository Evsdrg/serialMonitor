from __future__ import annotations

from unittest.mock import Mock

from core.connection_controller import (
    ConnectionController,
    ConnectionMode,
    Rfc2217ConnectionConfig,
    SerialConnectionConfig,
    TcpConnectionConfig,
)
from core.rfc2217_handler import Rfc2217Handler
from core.serial_handler import SerialHandler
from core.socket_handler import SocketHandler
from core.transport import (
    DisconnectReason,
    TransportOperation,
    TransportState,
    WriteDisposition,
)


def _controller(clock=lambda: 10.0):
    serial = SerialHandler()
    tcp = SocketHandler()
    rfc2217 = Rfc2217Handler()
    controller = ConnectionController(serial, tcp, rfc2217, clock=clock)
    return controller, serial, tcp, rfc2217


def test_controller_routes_connect_write_and_disconnect_to_active_transport():
    controller, _serial, tcp, _rfc2217 = _controller()
    tcp.open = Mock(return_value=True)
    tcp.write_data = Mock(return_value=True)
    tcp.close = Mock()
    assert controller.set_mode(ConnectionMode.TCP)
    config = TcpConnectionConfig("127.0.0.1", 9000)

    assert controller.connect(config)
    tcp.open.assert_called_once_with("127.0.0.1", 9000)

    tcp._transition(TransportState.CONNECTED)
    assert controller.write_data(b"hello") is True
    tcp.write_data.assert_called_once_with(b"hello")

    controller.disconnect()
    tcp.close.assert_called_once_with(reason=DisconnectReason.USER)
    assert controller.manual_disconnect is True


def test_rfc2217_write_reports_queued_disposition():
    controller, _serial, _tcp, rfc2217 = _controller()
    controller.set_mode(ConnectionMode.RFC2217)
    rfc2217._state = TransportState.CONNECTED
    worker = Mock()
    worker.enqueue.return_value = True
    rfc2217._worker = worker

    assert controller.write_payload(b"x") is WriteDisposition.QUEUED


def test_controller_forwards_only_active_transport_data(qtbot):
    controller, serial, tcp, _rfc2217 = _controller()
    received = []
    controller.data_received.connect(received.append)

    serial.data_received.emit(b"serial")
    tcp.data_received.emit(b"tcp")
    assert received == [b"serial"]

    assert controller.set_mode(ConnectionMode.TCP)
    tcp.data_received.emit(b"tcp")
    assert received == [b"serial", b"tcp"]


def test_controller_error_event_preserves_interactive_attempt(qtbot):
    controller, _serial, tcp, _rfc2217 = _controller()
    tcp.open = Mock(return_value=True)
    controller.set_mode(ConnectionMode.TCP)
    errors = []
    controller.error_occurred.connect(lambda *args: errors.append(args))

    controller.connect(TcpConnectionConfig("127.0.0.1", 9000), interactive=True)
    tcp._emit_error(
        TransportOperation.CONNECT,
        "refused",
        reason=DisconnectReason.CONNECT_FAILED,
    )

    mode, error, interactive = errors[-1]
    assert mode == ConnectionMode.TCP.value
    assert error.message == "refused"
    assert interactive is True
    assert controller.reconnect_deadline(ConnectionMode.TCP) == 15.0


def test_controller_reconnect_uses_saved_config_after_backoff(qtbot):
    now = [10.0]
    controller, _serial, tcp, _rfc2217 = _controller(clock=lambda: now[0])
    tcp.open = Mock(return_value=True)
    controller.set_mode(ConnectionMode.TCP)
    config = TcpConnectionConfig("127.0.0.1", 9000)
    controller.connect(config)
    tcp._transition(TransportState.CONNECTED)
    tcp._transition(TransportState.DISCONNECTED, DisconnectReason.REMOTE)

    assert controller.poll_reconnect(auto_reconnect=True) is False
    now[0] = 15.0
    assert controller.poll_reconnect(auto_reconnect=True) is True
    assert tcp.open.call_count == 2


def test_controller_serial_reconnect_requires_original_port(qtbot):
    now = [10.0]
    controller, serial, _tcp, _rfc2217 = _controller(clock=lambda: now[0])
    serial.open = Mock(return_value=True)
    serial.get_available_ports = Mock(return_value=["/dev/ttyUSB1"])
    config = SerialConnectionConfig(port="/dev/ttyUSB0")
    controller.connect(config)
    serial._transition(TransportState.DISCONNECTED, DisconnectReason.DEVICE_REMOVED)
    now[0] = 15.0

    assert controller.poll_reconnect(auto_reconnect=True) is False
    assert serial.open.call_count == 1


def test_controller_dispatches_rfc2217_configuration():
    controller, _serial, _tcp, rfc2217 = _controller()
    rfc2217.open = Mock(return_value=True)
    controller.set_mode(ConnectionMode.RFC2217)
    config = Rfc2217ConnectionConfig(
        host="example.test",
        port=2217,
        baudrate="115200",
        parity="Even",
        databits="8",
        stopbits="1",
        dtr=False,
        rts=True,
        network_timeout=2.5,
        ignore_set_control=True,
    )

    assert controller.connect(config)

    rfc2217.open.assert_called_once_with(
        "example.test",
        2217,
        baudrate="115200",
        parity="Even",
        databits="8",
        stopbits="1",
        dtr=False,
        rts=True,
        network_timeout=2.5,
        ignore_set_control=True,
    )
