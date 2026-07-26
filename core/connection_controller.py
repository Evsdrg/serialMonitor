"""Application-level connection state and transport routing."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal

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
    WriteDisposition,
)


class ConnectionMode(str, Enum):
    SERIAL = "serial"
    TCP = "tcp"
    RFC2217 = "rfc2217"


@dataclass(frozen=True)
class SerialConnectionConfig:
    port: str
    baudrate: int | str = 115200
    parity: str = "N"
    databits: int | str = 8
    stopbits: float | str = 1
    dtr: bool = True
    rts: bool = True

    @property
    def endpoint(self) -> str:
        return self.port


@dataclass(frozen=True)
class TcpConnectionConfig:
    host: str
    port: int

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass(frozen=True)
class Rfc2217ConnectionConfig:
    host: str
    port: int
    baudrate: int | str = 115200
    parity: str = "N"
    databits: int | str = 8
    stopbits: float | str = 1
    dtr: bool = True
    rts: bool = True
    network_timeout: float = 3.0
    ignore_set_control: bool = False

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"


ConnectionConfig = (
    SerialConnectionConfig | TcpConnectionConfig | Rfc2217ConnectionConfig
)


class ConnectionController(QObject):
    """Own connection intent, reconnect policy, and active transport routing."""

    data_received = pyqtSignal(bytes)
    state_changed = pyqtSignal(str, object)
    error_occurred = pyqtSignal(str, object, bool)
    reconnecting = pyqtSignal(str, str)

    def __init__(
        self,
        serial_handler: SerialHandler,
        socket_handler: SocketHandler,
        rfc2217_handler: Rfc2217Handler,
        *,
        clock: Callable[[], float] = time.monotonic,
        reconnect_delay: float = 5.0,
    ) -> None:
        super().__init__()
        self._clock = clock
        self._reconnect_delay = reconnect_delay
        self._mode = ConnectionMode.SERIAL
        self._handlers: dict[ConnectionMode, TransportHandler] = {
            ConnectionMode.SERIAL: serial_handler,
            ConnectionMode.TCP: socket_handler,
            ConnectionMode.RFC2217: rfc2217_handler,
        }
        self._configs: dict[ConnectionMode, ConnectionConfig | None] = {
            mode: None for mode in ConnectionMode
        }
        self._manual_disconnect = {mode: False for mode in ConnectionMode}
        self._interactive_attempt = {mode: False for mode in ConnectionMode}
        self._reconnect_deadlines = {mode: 0.0 for mode in ConnectionMode}
        self._signal_bindings: dict[ConnectionMode, tuple[object, object, object]] = {}

        for mode, handler in self._handlers.items():
            self._bind_handler(mode, handler)

    @property
    def mode(self) -> ConnectionMode:
        return self._mode

    @property
    def active_handler(self) -> TransportHandler:
        return self._handlers[self._mode]

    @property
    def state(self) -> TransportState:
        state = getattr(self.active_handler, "state", None)
        if isinstance(state, TransportState):
            return state
        if self.active_handler.is_open() is True:
            return TransportState.CONNECTED
        if getattr(self.active_handler, "is_connecting", lambda: False)() is True:
            return TransportState.CONNECTING
        return TransportState.DISCONNECTED

    @property
    def manual_disconnect(self) -> bool:
        return self._manual_disconnect[self._mode]

    @manual_disconnect.setter
    def manual_disconnect(self, value: bool) -> None:
        self._manual_disconnect[self._mode] = value

    def set_mode(self, mode: ConnectionMode | str) -> bool:
        next_mode = ConnectionMode(mode)
        if self.state is not TransportState.DISCONNECTED:
            return False
        self._mode = next_mode
        return True

    def is_connected(self) -> bool:
        return self.state is TransportState.CONNECTED

    def is_active(self) -> bool:
        return self.state is not TransportState.DISCONNECTED

    def current_config(
        self, mode: ConnectionMode | str | None = None
    ) -> ConnectionConfig | None:
        return self._configs[ConnectionMode(mode) if mode is not None else self._mode]

    def remember_config(self, config: ConnectionConfig) -> None:
        self._configs[self._mode_for_config(config)] = config

    def handler(self, mode: ConnectionMode | str) -> TransportHandler:
        return self._handlers[ConnectionMode(mode)]

    def replace_handler(
        self, mode: ConnectionMode | str, handler: TransportHandler
    ) -> None:
        connection_mode = ConnectionMode(mode)
        old_handler = self._handlers[connection_mode]
        bindings = self._signal_bindings.get(connection_mode)
        if bindings is not None:
            for signal_name, slot in zip(
                ("data_received", "state_changed", "transport_error"), bindings
            ):
                try:
                    getattr(old_handler, signal_name).disconnect(slot)
                except (AttributeError, TypeError):
                    pass
        self._handlers[connection_mode] = handler
        self._bind_handler(connection_mode, handler)

    def reconnect_deadline(self, mode: ConnectionMode | str) -> float:
        return self._reconnect_deadlines[ConnectionMode(mode)]

    def connect(self, config: ConnectionConfig, *, interactive: bool = True) -> bool:
        mode = self._mode_for_config(config)
        if mode is not self._mode:
            return False
        if self.state is not TransportState.DISCONNECTED:
            return True

        self._configs[mode] = config
        self._manual_disconnect[mode] = False
        self._interactive_attempt[mode] = interactive
        self._reconnect_deadlines[mode] = 0.0
        accepted = self._open_config(mode, config)
        if not accepted:
            self._reconnect_deadlines[mode] = self._clock() + self._reconnect_delay
        return accepted

    def disconnect(
        self, reason: DisconnectReason = DisconnectReason.USER
    ) -> None:
        if reason is DisconnectReason.USER:
            self._manual_disconnect[self._mode] = True
            self._reconnect_deadlines[self._mode] = 0.0
        if self.state is TransportState.DISCONNECTED:
            return
        if isinstance(self.active_handler, TransportHandler):
            self.active_handler.close(reason=reason)  # type: ignore[attr-defined]
        else:
            self.active_handler.close()  # type: ignore[attr-defined]

    def write_data(self, data: bytes) -> bool:
        return self.write_payload(data) is not WriteDisposition.REJECTED

    def write_payload(self, data: bytes) -> WriteDisposition:
        handler = self.active_handler
        if not handler.write_data(data):
            return WriteDisposition.REJECTED
        if self._mode is ConnectionMode.RFC2217 or handler.has_pending_writes():
            return WriteDisposition.QUEUED
        return WriteDisposition.SENT

    def connection_error(self) -> str:
        return self.active_handler.last_error or ""

    def set_dtr(self, level: bool) -> bool:
        setter = getattr(self.active_handler, "set_dtr", None)
        if not callable(setter):
            return False
        result = setter(level)
        return True if result is None else bool(result)

    def set_rts(self, level: bool) -> bool:
        setter = getattr(self.active_handler, "set_rts", None)
        if not callable(setter):
            return False
        result = setter(level)
        return True if result is None else bool(result)

    def poll_reconnect(self, *, auto_reconnect: bool) -> bool:
        mode = self._mode
        config = self._configs[mode]
        if (
            not auto_reconnect
            or self._manual_disconnect[mode]
            or config is None
            or self.state is not TransportState.DISCONNECTED
            or self._clock() < self._reconnect_deadlines[mode]
        ):
            return False

        if isinstance(config, SerialConnectionConfig):
            serial_handler = self._handlers[ConnectionMode.SERIAL]
            if config.port not in serial_handler.get_available_ports():  # type: ignore[attr-defined]
                return False

        self._interactive_attempt[mode] = False
        self._reconnect_deadlines[mode] = self._clock() + self._reconnect_delay
        self.reconnecting.emit(mode.value, config.endpoint)
        return self._open_config(mode, config)

    @staticmethod
    def _mode_for_config(config: ConnectionConfig) -> ConnectionMode:
        if isinstance(config, SerialConnectionConfig):
            return ConnectionMode.SERIAL
        if isinstance(config, TcpConnectionConfig):
            return ConnectionMode.TCP
        return ConnectionMode.RFC2217

    def _open_config(self, mode: ConnectionMode, config: ConnectionConfig) -> bool:
        handler = self._handlers[mode]
        if isinstance(config, SerialConnectionConfig):
            return handler.open(  # type: ignore[attr-defined]
                port=config.port,
                baudrate=config.baudrate,
                parity=config.parity,
                databits=config.databits,
                stopbits=config.stopbits,
                dtr=config.dtr,
                rts=config.rts,
            )
        if isinstance(config, TcpConnectionConfig):
            return handler.open(config.host, config.port)  # type: ignore[attr-defined]
        return handler.open(  # type: ignore[attr-defined]
            config.host,
            config.port,
            baudrate=config.baudrate,
            parity=config.parity,
            databits=config.databits,
            stopbits=config.stopbits,
            dtr=config.dtr,
            rts=config.rts,
            network_timeout=config.network_timeout,
            ignore_set_control=config.ignore_set_control,
        )

    def _on_data(self, mode: ConnectionMode, data: bytes) -> None:
        if mode is self._mode:
            self.data_received.emit(data)

    def _on_state_changed(
        self, mode: ConnectionMode, transition: TransportTransition
    ) -> None:
        if transition.current is TransportState.CONNECTED:
            self._interactive_attempt[mode] = False
            self._reconnect_deadlines[mode] = 0.0
        elif transition.current is TransportState.DISCONNECTED:
            if transition.reason in (
                DisconnectReason.USER,
                DisconnectReason.SHUTDOWN,
            ):
                self._manual_disconnect[mode] = True
            elif not self._manual_disconnect[mode]:
                self._reconnect_deadlines[mode] = (
                    self._clock() + self._reconnect_delay
                )
        self.state_changed.emit(mode.value, transition)

    def _on_error(self, mode: ConnectionMode, error: TransportError) -> None:
        interactive = (
            error.operation is TransportOperation.CONNECT
            and self._interactive_attempt[mode]
        )
        if error.operation is TransportOperation.CONNECT:
            self._reconnect_deadlines[mode] = self._clock() + self._reconnect_delay
        self.error_occurred.emit(mode.value, error, interactive)

    def _bind_handler(
        self, mode: ConnectionMode, handler: TransportHandler
    ) -> None:
        data_slot = partial(self._on_data, mode)
        state_slot = partial(self._on_state_changed, mode)
        error_slot = partial(self._on_error, mode)
        self._signal_bindings[mode] = (data_slot, state_slot, error_slot)
        for signal_name, slot in (
            ("data_received", data_slot),
            ("state_changed", state_slot),
            ("transport_error", error_slot),
        ):
            signal = getattr(handler, signal_name, None)
            connect = getattr(signal, "connect", None)
            if callable(connect):
                connect(slot)
