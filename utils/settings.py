"""Typed application settings with legacy migration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any


def _string(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _boolean(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _integer(
    value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None
) -> int:
    if isinstance(value, bool):
        return default
    try:
        result = int(value)
    except (OverflowError, TypeError, ValueError):
        return default
    if minimum is not None and result < minimum:
        return default
    if maximum is not None and result > maximum:
        return default
    return result


def _number(value: Any, default: float, *, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    if minimum is not None and result < minimum:
        return default
    return result


def _port(value: Any) -> int | None:
    result = _integer(value, 0, minimum=1, maximum=65535)
    return result or None


def _valid_geometry(value: Any) -> str:
    geometry = _string(value)
    if not geometry:
        return ""
    try:
        bytes.fromhex(geometry)
    except ValueError:
        return ""
    return geometry


@dataclass(frozen=True)
class SerialSettings:
    port: str = ""
    baudrate: str = "115200"
    parity: str = "None"
    databits: str = "8"
    stopbits: str = "1"
    dtr: bool = False
    rts: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SerialSettings":
        return cls(
            port=_string(data.get("port")),
            baudrate=_string(data.get("baudrate"), "115200"),
            parity=_string(data.get("parity"), "None"),
            databits=_string(data.get("databits"), "8"),
            stopbits=_string(data.get("stopbits"), "1"),
            dtr=_boolean(data.get("dtr"), False),
            rts=_boolean(data.get("rts"), False),
        )


@dataclass(frozen=True)
class TcpSettings:
    host: str = ""
    port: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TcpSettings":
        return cls(host=_string(data.get("host")), port=_port(data.get("port")))


@dataclass(frozen=True)
class Rfc2217Settings:
    host: str = ""
    port: int | None = None
    baudrate: str = "115200"
    parity: str = "None"
    databits: str = "8"
    stopbits: str = "1"
    dtr: bool = False
    rts: bool = False
    network_timeout: float = 3.0
    ignore_set_control: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rfc2217Settings":
        return cls(
            host=_string(data.get("host")),
            port=_port(data.get("port")),
            baudrate=_string(data.get("baudrate"), "115200"),
            parity=_string(data.get("parity"), "None"),
            databits=_string(data.get("databits"), "8"),
            stopbits=_string(data.get("stopbits"), "1"),
            dtr=_boolean(data.get("dtr"), False),
            rts=_boolean(data.get("rts"), False),
            network_timeout=_number(
                data.get("network_timeout"), 3.0, minimum=0.01
            ),
            ignore_set_control=_boolean(
                data.get("ignore_set_control"), False
            ),
        )


@dataclass(frozen=True)
class AppSettings:
    schema_version: int = 2
    geometry: str = ""
    language: str = "zh"
    theme_index: int = 0
    connection_mode: str = "serial"
    serial: SerialSettings = SerialSettings()
    tcp: TcpSettings = TcpSettings()
    rfc2217: Rfc2217Settings = Rfc2217Settings()
    receive_hex_mode: bool = False
    send_hex_mode: bool = False
    auto_scroll: bool = True
    show_timestamp: bool = True
    enable_ansi_colors: bool = True
    auto_reconnect: bool = False
    auto_checksum: bool = False
    checksum_start: int = 1
    checksum_end_mode: int = 0
    terminal_mode: bool = False
    trim_enabled: bool = True
    max_terminal_lines: int = 5000
    trim_batch_lines: int = 800

    @classmethod
    def from_dict(cls, raw: Any) -> "AppSettings":
        data = raw if isinstance(raw, dict) else {}
        connections = data.get("connections")
        if data.get("schema_version") == 2 and isinstance(connections, dict):
            serial_data = connections.get("serial", {})
            tcp_data = connections.get("tcp", {})
            rfc_data = connections.get("rfc2217", {})
        else:
            shared_serial = {
                "port": data.get("serial_port", ""),
                "baudrate": data.get("baudrate", "115200"),
                "parity": data.get("parity", "None"),
                "databits": data.get("databits", "8"),
                "stopbits": data.get("stopbits", "1"),
                "dtr": data.get("dtr_state", False),
                "rts": data.get("rts_state", False),
            }
            serial_data = shared_serial
            tcp_data = {
                "host": data.get("socket_host", ""),
                "port": data.get("socket_port"),
            }
            rfc_data = {
                **shared_serial,
                "host": data.get("socket_host", ""),
                "port": data.get("socket_port"),
                "network_timeout": data.get("rfc2217_timeout", 3.0),
                "ignore_set_control": data.get(
                    "rfc2217_ignore_set_control", False
                ),
            }

        if not isinstance(serial_data, dict):
            serial_data = {}
        if not isinstance(tcp_data, dict):
            tcp_data = {}
        if not isinstance(rfc_data, dict):
            rfc_data = {}
        mode = _string(data.get("connection_mode"), "serial")
        if mode not in ("serial", "tcp", "rfc2217"):
            mode = "serial"
        language = _string(data.get("language"), "zh")
        if language not in ("zh", "en"):
            language = "zh"

        return cls(
            geometry=_valid_geometry(data.get("geometry")),
            language=language,
            theme_index=_integer(
                data.get("theme_index"), 0, minimum=0, maximum=2
            ),
            connection_mode=mode,
            serial=SerialSettings.from_dict(serial_data),
            tcp=TcpSettings.from_dict(tcp_data),
            rfc2217=Rfc2217Settings.from_dict(rfc_data),
            receive_hex_mode=_boolean(data.get("receive_hex_mode"), False),
            send_hex_mode=_boolean(data.get("send_hex_mode"), False),
            auto_scroll=_boolean(data.get("auto_scroll"), True),
            show_timestamp=_boolean(data.get("show_timestamp"), True),
            enable_ansi_colors=_boolean(data.get("enable_ansi_colors"), True),
            auto_reconnect=_boolean(data.get("auto_reconnect"), False),
            auto_checksum=_boolean(data.get("auto_checksum"), False),
            checksum_start=_integer(
                data.get("checksum_start"), 1, minimum=1, maximum=9999
            ),
            checksum_end_mode=_integer(
                data.get("checksum_end_mode"), 0, minimum=0, maximum=4
            ),
            terminal_mode=_boolean(data.get("terminal_mode"), False),
            trim_enabled=_boolean(data.get("trim_enabled"), True),
            max_terminal_lines=_integer(
                data.get("max_terminal_lines"), 5000, minimum=1, maximum=10_000_000
            ),
            trim_batch_lines=_integer(
                data.get("trim_batch_lines"), 800, minimum=1, maximum=10_000_000
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "geometry": self.geometry,
            "language": self.language,
            "theme_index": self.theme_index,
            "connection_mode": self.connection_mode,
            "connections": {
                "serial": asdict(self.serial),
                "tcp": asdict(self.tcp),
                "rfc2217": asdict(self.rfc2217),
            },
            "receive_hex_mode": self.receive_hex_mode,
            "send_hex_mode": self.send_hex_mode,
            "auto_scroll": self.auto_scroll,
            "show_timestamp": self.show_timestamp,
            "enable_ansi_colors": self.enable_ansi_colors,
            "auto_reconnect": self.auto_reconnect,
            "auto_checksum": self.auto_checksum,
            "checksum_start": self.checksum_start,
            "checksum_end_mode": self.checksum_end_mode,
            "terminal_mode": self.terminal_mode,
            "trim_enabled": self.trim_enabled,
            "max_terminal_lines": self.max_terminal_lines,
            "trim_batch_lines": self.trim_batch_lines,
        }
