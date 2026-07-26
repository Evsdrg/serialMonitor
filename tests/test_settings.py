from utils.settings import AppSettings


def test_legacy_settings_migrate_shared_network_fields_deterministically():
    settings = AppSettings.from_dict(
        {
            "connection_mode": "rfc2217",
            "socket_host": "192.0.2.10",
            "socket_port": "2217",
            "baudrate": "57600",
            "parity": "Even",
            "dtr_state": True,
            "rts_state": False,
            "rfc2217_timeout": 2.5,
            "rfc2217_ignore_set_control": True,
        }
    )

    assert settings.schema_version == 2
    assert settings.tcp.host == "192.0.2.10"
    assert settings.tcp.port == 2217
    assert settings.rfc2217.host == "192.0.2.10"
    assert settings.rfc2217.port == 2217
    assert settings.serial.baudrate == "57600"
    assert settings.rfc2217.baudrate == "57600"
    assert settings.rfc2217.ignore_set_control is True


def test_nested_settings_round_trip_keeps_tcp_and_rfc2217_independent():
    raw = {
        "schema_version": 2,
        "connection_mode": "tcp",
        "connections": {
            "serial": {"port": "/dev/ttyUSB0", "baudrate": "115200"},
            "tcp": {"host": "tcp.example", "port": 9000},
            "rfc2217": {
                "host": "rfc.example",
                "port": 2217,
                "baudrate": "38400",
                "network_timeout": 1.5,
            },
        },
    }

    settings = AppSettings.from_dict(raw)
    encoded = settings.to_dict()

    assert encoded["connections"]["tcp"] == {
        "host": "tcp.example",
        "port": 9000,
    }
    assert encoded["connections"]["rfc2217"]["host"] == "rfc.example"
    assert encoded["connections"]["rfc2217"]["baudrate"] == "38400"


def test_invalid_typed_values_fall_back_without_raising():
    settings = AppSettings.from_dict(
        {
            "schema_version": 2,
            "geometry": "not-hex",
            "connection_mode": "unknown",
            "connections": {
                "tcp": {"host": 123, "port": 70000},
                "rfc2217": {"network_timeout": -1},
            },
            "max_terminal_lines": "bad",
        }
    )

    assert settings.geometry == ""
    assert settings.connection_mode == "serial"
    assert settings.tcp.host == ""
    assert settings.tcp.port is None
    assert settings.rfc2217.network_timeout == 3.0
    assert settings.max_terminal_lines == 5000


def test_all_protocol_checksum_end_modes_round_trip():
    for mode in range(5):
        settings = AppSettings.from_dict(
            {"schema_version": 2, "connections": {}, "checksum_end_mode": mode}
        )

        assert settings.checksum_end_mode == mode


def test_huge_integer_network_timeout_falls_back():
    settings = AppSettings.from_dict(
        {
            "schema_version": 2,
            "connections": {"rfc2217": {"network_timeout": 10**400}},
        }
    )

    assert settings.rfc2217.network_timeout == 3.0


def test_out_of_range_integers_fall_back():
    settings = AppSettings.from_dict(
        {
            "schema_version": 2,
            "connections": {},
            "theme_index": 7,
            "checksum_start": 10**400,
            "max_terminal_lines": 10**400,
            "trim_batch_lines": 10**400,
        }
    )

    assert settings.theme_index == 0
    assert settings.checksum_start == 1
    assert settings.max_terminal_lines == 5000
    assert settings.trim_batch_lines == 800


def test_non_finite_network_timeout_falls_back():
    settings = AppSettings.from_dict(
        {
            "schema_version": 2,
            "connections": {"rfc2217": {"network_timeout": "NaN"}},
        }
    )

    assert settings.rfc2217.network_timeout == 3.0


def test_overflowing_integer_settings_fall_back():
    settings = AppSettings.from_dict(
        {"checksum_start": 1e309, "max_terminal_lines": 1e309}
    )

    assert settings.checksum_start == 1
    assert settings.max_terminal_lines == 5000


def test_invalid_terminal_mode_falls_back_to_false():
    for bad in ("yes", 1, 0, None, []):
        settings = AppSettings.from_dict({"terminal_mode": bad})
        assert settings.terminal_mode is False
