from utils.settings import Rfc2217Settings, TcpSettings

from ui.connection_panel import ConnectionPanel


def test_mode_controls_have_distinct_visibility(qtbot):
    panel = ConnectionPanel()
    qtbot.addWidget(panel)
    panel.show()

    panel.set_mode("tcp")
    assert panel.socket_host_input.isVisible() is True
    assert panel.port_combo.isVisible() is False
    assert panel.baudrate_combo.isVisible() is False

    panel.set_mode("rfc2217")
    assert panel.socket_host_input.isVisible() is True
    assert panel.baudrate_combo.isVisible() is True
    assert panel.rfc2217_timeout_spinbox.isVisible() is True


def test_capture_and_apply_typed_settings(qtbot):
    panel = ConnectionPanel()
    qtbot.addWidget(panel)
    expected = Rfc2217Settings(
        host="rfc.example",
        port=2217,
        baudrate="38400",
        network_timeout=2.5,
        ignore_set_control=True,
    )

    panel.apply_settings("rfc2217", expected)

    assert panel.capture_settings("rfc2217") == expected


def test_tcp_invalid_port_is_captured_as_none(qtbot):
    panel = ConnectionPanel()
    qtbot.addWidget(panel)
    panel.apply_settings("tcp", TcpSettings("tcp.example", 9000))
    panel.socket_port_input.setText("")

    assert panel.capture_settings("tcp") == TcpSettings("tcp.example", None)


def test_control_lines_remain_available_while_connected(qtbot):
    panel = ConnectionPanel()
    qtbot.addWidget(panel)

    panel.set_controls_enabled(False, mode="serial", is_connected=True)

    assert panel.baudrate_combo.isEnabled() is False
    assert panel.dtr_checkbox.isEnabled() is True
    assert panel.rts_checkbox.isEnabled() is True


def test_panel_emits_user_commands(qtbot):
    panel = ConnectionPanel()
    qtbot.addWidget(panel)

    with qtbot.waitSignal(panel.mode_requested):
        panel.connection_mode_button.click()
    with qtbot.waitSignal(panel.connect_requested):
        panel.connect_button.click()
    with qtbot.waitSignal(panel.refresh_requested):
        panel.refresh_button.click()
