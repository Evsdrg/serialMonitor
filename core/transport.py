"""Shared transport state and event contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import QObject, pyqtSignal


class TransportState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CLOSING = "closing"


class DisconnectReason(str, Enum):
    USER = "user"
    REMOTE = "remote"
    CONNECT_FAILED = "connect_failed"
    IO_ERROR = "io_error"
    DEVICE_REMOVED = "device_removed"
    SHUTDOWN = "shutdown"


class TransportOperation(str, Enum):
    CONNECT = "connect"
    READ = "read"
    WRITE = "write"
    CONTROL = "control"
    SHUTDOWN = "shutdown"


class WriteDisposition(str, Enum):
    SENT = "sent"
    QUEUED = "queued"
    REJECTED = "rejected"


@dataclass(frozen=True)
class TransportTransition:
    previous: TransportState
    current: TransportState
    endpoint: str
    reason: DisconnectReason | None = None
    session_was_connected: bool = False


@dataclass(frozen=True)
class TransportError:
    operation: TransportOperation
    message: str
    endpoint: str
    reason: DisconnectReason | None = None


class TransportHandler(QObject):
    """Common observable contract implemented by every transport."""

    data_received = pyqtSignal(bytes)
    connection_changed = pyqtSignal(bool, str)
    error_occurred = pyqtSignal(str)
    state_changed = pyqtSignal(object)
    transport_error = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self._state = TransportState.DISCONNECTED
        self._session_was_connected = False
        self.last_error: str | None = None
        self.last_error_context: str | None = None

    @property
    def endpoint(self) -> str:
        return ""

    @property
    def state(self) -> TransportState:
        return self._state

    def is_open(self) -> bool:
        return self._state is TransportState.CONNECTED

    def is_connecting(self) -> bool:
        return self._state in (
            TransportState.CONNECTING,
            TransportState.CLOSING,
        )

    def write_data(self, data: bytes) -> bool:
        raise NotImplementedError

    def _transition(
        self,
        state: TransportState,
        reason: DisconnectReason | None = None,
    ) -> None:
        previous = self._state
        if previous is state:
            return
        if (
            state is TransportState.CONNECTING
            and previous is TransportState.DISCONNECTED
        ):
            self._session_was_connected = False
        elif state is TransportState.CONNECTED:
            self._session_was_connected = True
        self._state = state
        self.state_changed.emit(
            TransportTransition(
                previous,
                state,
                self.endpoint,
                reason,
                self._session_was_connected,
            )
        )
        if state is TransportState.CONNECTED:
            self.connection_changed.emit(True, self.endpoint)
        elif state is TransportState.DISCONNECTED:
            self.connection_changed.emit(False, self.endpoint)
            self._session_was_connected = False

    def _emit_error(
        self,
        operation: TransportOperation,
        message: str,
        *,
        reason: DisconnectReason | None = None,
        legacy_context: str | None = None,
    ) -> None:
        self.last_error = message
        self.last_error_context = legacy_context or (
            "connect" if operation is TransportOperation.CONNECT else "io"
        )
        self.transport_error.emit(
            TransportError(operation, message, self.endpoint, reason)
        )
        self.error_occurred.emit(message)
