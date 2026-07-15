from __future__ import annotations

import pytest

from core.rfc2217_handler import Rfc2217Handler
from core.serial_handler import SerialHandler
from core.socket_handler import SocketHandler
from core.transport import (
    DisconnectReason,
    TransportError,
    TransportHandler,
    TransportOperation,
    TransportState,
    TransportTransition,
)


class _FakeTransport(TransportHandler):
    @property
    def endpoint(self) -> str:
        return "fake:1"


@pytest.mark.parametrize(
    "factory", [SerialHandler, SocketHandler, Rfc2217Handler]
)
def test_transport_common_initial_contract(factory):
    handler = factory()

    assert isinstance(handler, TransportHandler)
    assert handler.state is TransportState.DISCONNECTED
    assert handler.is_open() is False
    assert handler.is_connecting() is False
    assert handler.write_data(b"x") is False


def test_transport_transition_event_is_self_contained(qtbot):
    handler = _FakeTransport()

    with qtbot.waitSignal(handler.state_changed, timeout=1000) as blocker:
        handler._transition(TransportState.CONNECTING)

    transition = blocker.args[0]
    assert transition == TransportTransition(
        previous=TransportState.DISCONNECTED,
        current=TransportState.CONNECTING,
        endpoint="fake:1",
        reason=None,
    )


def test_transport_disconnected_transition_keeps_legacy_signal(qtbot):
    handler = _FakeTransport()
    handler._transition(TransportState.CONNECTING)
    handler._transition(TransportState.CONNECTED)

    with qtbot.waitSignal(handler.connection_changed, timeout=1000) as blocker:
        handler._transition(
            TransportState.DISCONNECTED, DisconnectReason.REMOTE
        )

    assert blocker.args == [False, "fake:1"]


def test_disconnect_transition_remembers_connected_session(qtbot):
    handler = _FakeTransport()
    transitions = []
    handler.state_changed.connect(transitions.append)
    handler._transition(TransportState.CONNECTING)
    handler._transition(TransportState.CONNECTED)
    handler._transition(TransportState.CLOSING, DisconnectReason.USER)
    handler._transition(TransportState.DISCONNECTED, DisconnectReason.USER)

    assert transitions[-1].previous is TransportState.CLOSING
    assert transitions[-1].session_was_connected is True


def test_transport_error_event_contains_operation_and_endpoint(qtbot):
    handler = _FakeTransport()

    with qtbot.waitSignal(handler.transport_error, timeout=1000) as blocker:
        handler._emit_error(TransportOperation.WRITE, "short write")

    error = blocker.args[0]
    assert error == TransportError(
        operation=TransportOperation.WRITE,
        message="short write",
        endpoint="fake:1",
        reason=None,
    )
    assert handler.last_error == "short write"
    assert handler.last_error_context == "io"
