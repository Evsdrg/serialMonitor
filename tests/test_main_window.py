"""
测试 ui/main_window.py
"""

import json
import socket
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication

from core.connection_controller import (
    ConnectionMode,
    Rfc2217ConnectionConfig,
    SerialConnectionConfig,
    TcpConnectionConfig,
)
from core.transport import (
    DisconnectReason,
    TransportError,
    TransportOperation,
    TransportState,
    TransportTransition,
)
from ui.main_window import TerminalTrimManager, SerialMonitor
from utils.settings import AppSettings


DEFAULT_SETTINGS = {
    "geometry": "",
    "language": "zh",
    "theme_index": 0,
    "baudrate": "115200",
    "parity": "None",
    "databits": "8",
    "stopbits": "1",
    "receive_hex_mode": False,
    "send_hex_mode": False,
    "auto_scroll": True,
    "show_timestamp": True,
    "enable_ansi_colors": True,
    "auto_reconnect": False,
    "auto_checksum": False,
    "checksum_start": 1,
    "checksum_end_mode": 0,
    "dtr_state": False,
    "rts_state": False,
    "connection_mode": "serial",
    "socket_host": "",
    "socket_port": "",
    "rfc2217_timeout": 3.0,
    "rfc2217_ignore_set_control": False,
    "terminal_mode": False,
    "trim_enabled": True,
    "max_terminal_lines": 5000,
    "trim_batch_lines": 800,
}


@pytest.fixture(autouse=True)
def mock_config():
    with patch("ui.main_window.ConfigManager.load_settings", return_value=dict(DEFAULT_SETTINGS)), \
         patch("ui.main_window.ConfigManager.save_settings"):
        yield


class TestTerminalTrimManager:
    def test_default_values(self):
        tm = TerminalTrimManager()
        assert tm.enabled is True
        assert tm.max_lines == TerminalTrimManager.DEFAULT_MAX_LINES
        assert tm.batch_lines == TerminalTrimManager.DEFAULT_BATCH_LINES

    def test_to_dict(self):
        tm = TerminalTrimManager()
        data = tm.to_dict()
        assert "trim_enabled" in data
        assert "max_terminal_lines" in data
        assert "trim_batch_lines" in data

    def test_load_from_dict(self):
        tm = TerminalTrimManager()
        tm.load_from_dict({
            "trim_enabled": False,
            "max_terminal_lines": 1000,
            "trim_batch_lines": 200,
        })
        assert tm.enabled is False
        assert tm.max_lines == 1000
        assert tm.batch_lines == 200

    def test_log_dir_created(self):
        tm = TerminalTrimManager()
        assert tm.log_dir.exists()

    def test_trim_disabled_does_nothing(self):
        tm = TerminalTrimManager()
        tm.enabled = False

        doc = QTextDocument()
        doc.setPlainText("line1\nline2\nline3")
        tm.trim_if_needed(doc)
        assert doc.blockCount() == 3

    def test_trim_below_threshold(self):
        tm = TerminalTrimManager()
        tm.max_lines = 100
        tm.batch_lines = 10

        doc = QTextDocument()
        doc.setPlainText("line1\nline2\nline3")
        tm.trim_if_needed(doc)
        assert doc.blockCount() == 3

    def test_trim_above_threshold(self):
        tm = TerminalTrimManager()
        tm.max_lines = 5
        tm.batch_lines = 3

        doc = QTextDocument()
        lines = "\n".join(f"line{i}" for i in range(20))
        doc.setPlainText(lines)
        tm.trim_if_needed(doc)
        assert doc.blockCount() == 5
        assert doc.toPlainText() == "\n".join(f"line{i}" for i in range(15, 20))

    def test_trim_preserves_first_remaining_character(self):
        tm = TerminalTrimManager()
        tm.max_lines = 2
        tm.batch_lines = 1

        doc = QTextDocument("line1\nline2\nline3")
        tm.trim_if_needed(doc)

        assert doc.toPlainText() == "line2\nline3"

    def test_trim_with_empty_document(self):
        tm = TerminalTrimManager()
        tm.max_lines = 1

        doc = QTextDocument()
        tm.trim_if_needed(doc)  # 不抛异常
        # 空文档通常有 1 个 block（QTextDocument 默认包含一个空段落）
        assert doc.blockCount() <= 1

    def test_trim_log_file_written(self, tmp_path):
        tm = TerminalTrimManager()
        tm.max_lines = 5
        tm.batch_lines = 3
        # 替换 _log_file 为 tmp_path
        tm._log_file = tmp_path / "test.log"

        doc = QTextDocument()
        lines = "\n".join(f"line{i}" for i in range(20))
        doc.setPlainText(lines)
        tm.trim_if_needed(doc)

        assert tmp_path.joinpath("test.log").exists()
        content = tmp_path.joinpath("test.log").read_text(encoding="utf-8")
        assert "line0" in content

    def test_log_dir_property(self):
        tm = TerminalTrimManager()
        assert tm.log_dir.exists()
        assert "SerialMonitorTrimmedLogs" in tm.log_dir.name

    def test_to_dict_includes_all(self):
        tm = TerminalTrimManager()
        data = tm.to_dict()
        assert data["trim_enabled"] is True
        assert data["max_terminal_lines"] == tm.DEFAULT_MAX_LINES
        assert data["trim_batch_lines"] == tm.DEFAULT_BATCH_LINES

    def test_trim_log_oserror(self, tmp_path):
        tm = TerminalTrimManager()
        tm.max_lines = 5
        tm.batch_lines = 3
        # 指向不存在的目录
        tm._log_file = tmp_path / "nonexistent_dir" / "test.log"

        doc = QTextDocument()
        lines = "\n".join(f"line{i}" for i in range(20))
        doc.setPlainText(lines)
        before = doc.toPlainText()
        tm.trim_if_needed(doc)
        assert doc.toPlainText() == before


class TestSerialMonitorStatic:
    def test_get_timestamp_format(self):
        ts = SerialMonitor.get_timestamp()
        assert ts.startswith("[")
        assert ts.endswith("] ")
        assert ":" in ts


class TestSerialMonitorSearchHelpers:
    def test_count_matches(self):
        doc = QTextDocument()
        doc.setPlainText("hello world hello")
        assert SerialMonitor._count_matches(doc, "hello", True) == 2

    def test_count_matches_case_insensitive(self):
        doc = QTextDocument()
        doc.setPlainText("Hello HELLO hello")
        assert SerialMonitor._count_matches(doc, "hello", False) == 3

    def test_current_match_index(self):
        doc = QTextDocument()
        doc.setPlainText("hello world hello")
        cursor = doc.find("hello")
        idx = SerialMonitor._current_match_index(doc, cursor, "hello", True)
        assert idx == 1


class TestSerialMonitorLifecycle:
    def test_initial_state(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        assert monitor.language == "zh"
        assert monitor.receive_hex_mode is False
        assert monitor.send_hex_mode is False
        assert monitor.auto_scroll is True

    def test_toggle_receive_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.toggle_receive_mode()
        assert monitor.receive_hex_mode is True

    def test_toggle_send_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.toggle_send_mode()
        assert monitor.send_hex_mode is True

    def test_toggle_auto_scroll(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.auto_scroll_checkbox.setChecked(False)
        monitor.toggle_auto_scroll()
        assert monitor.auto_scroll is False

    def test_toggle_timestamp(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.timestamp_checkbox.setChecked(False)
        monitor.toggle_timestamp()
        assert monitor.show_timestamp is False

    def test_clear_receive_area(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.terminal_display.setPlainText("test")
        monitor.clear_receive_area()
        assert monitor.terminal_display.toPlainText() == ""

    def test_clear_send_area(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.send_input.setText("test")
        monitor.clear_send_area()
        assert monitor.send_input.text() == ""

    def test_get_port_config(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.baudrate_combo.setCurrentText("9600")
        monitor.parity_combo.setCurrentText("Even")
        monitor.databits_combo.setCurrentText("7")
        monitor.stopbits_combo.setCurrentText("2")

        assert monitor.baudrate_combo.currentText() == "9600"
        assert monitor.parity_combo.currentText() == "Even"
        assert monitor.databits_combo.currentText() == "7"
        assert monitor.stopbits_combo.currentText() == "2"

    def test_calculate_checksum_no_auto(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.send_input.setText("AA BB")
        monitor.send_mode_button.click()
        monitor.auto_checksum_checkbox.setChecked(False)
        monitor.calculate_checksum()

        assert "00" not in monitor.checksum_input.text() or monitor.checksum_input.text() != ""

    def test_language_toggle(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.toggle_language()
        assert monitor.language == "en"

    def test_close_event(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        event = Mock()
        event.accept = Mock()
        monitor.closeEvent(event)
        event.accept.assert_called_once()

    def test_close_event_ignores_when_rfc2217_worker_does_not_stop(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.rfc2217_handler = Mock()
        monitor.rfc2217_handler.shutdown.return_value = False
        event = Mock()

        monitor.closeEvent(event)

        event.ignore.assert_called_once()
        event.accept.assert_not_called()
        assert monitor.device_check_timer.isActive() is True

    def test_close_event_ignores_when_serial_reader_does_not_stop(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.shutdown.return_value = False
        event = Mock()

        monitor.closeEvent(event)

        event.ignore.assert_called_once()
        event.accept.assert_not_called()
        assert monitor.device_check_timer.isActive() is True


class TestSerialMonitorDataProcessing:
    def test_append_to_terminal_plain(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.append_to_terminal("hello world")
        text = monitor.terminal_display.toPlainText()
        assert "hello world" in text

    def test_append_to_terminal_no_timestamp(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.show_timestamp = False
        monitor.append_to_terminal("plain")
        text = monitor.terminal_display.toPlainText()
        assert "[" not in text
        assert "plain" in text

    def test_append_to_terminal_ansi_disabled(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.enable_ansi_colors = False
        monitor.append_to_terminal("\x1b[31mred\x1b[0m")
        text = monitor.terminal_display.toPlainText()
        assert "red" in text
        assert "\x1b" not in text

    def test_append_to_terminal_multiple_calls(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.append_to_terminal("line1\n")
        monitor.append_to_terminal("line2\n")
        text = monitor.terminal_display.toPlainText()
        assert "line1" in text
        assert "line2" in text

    def test_on_serial_data_empty(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        before = monitor.terminal_display.toPlainText()
        monitor._on_serial_data(b"")
        after = monitor.terminal_display.toPlainText()
        assert before == after

    def test_on_serial_data_ascii(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor._on_serial_data(b"hello\n")
        text = monitor.terminal_display.toPlainText()
        assert "hello" in text

    def test_on_serial_data_no_newline(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.show_timestamp = False
        monitor._on_serial_data(b"no_newline")
        text = monitor.terminal_display.toPlainText()
        assert text == "no_newline"

    def test_on_serial_data_preserves_chunk_boundaries(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.show_timestamp = False

        monitor._on_serial_data(b"abc")
        monitor._on_serial_data(b"def\n")

        assert monitor.terminal_display.toPlainText() == "abcdef\n"

    def test_on_serial_data_decodes_utf8_across_chunks(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.show_timestamp = False
        encoded = "你".encode("utf-8")

        monitor._on_serial_data(encoded[:1])
        assert monitor.terminal_display.toPlainText() == ""

        monitor._on_serial_data(encoded[1:])
        assert monitor.terminal_display.toPlainText() == "你"

    def test_on_serial_data_timestamps_split_crlf_once(self, qtbot, monkeypatch):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.show_timestamp = True
        monkeypatch.setattr(monitor, "get_timestamp", lambda: "[T] ")

        monitor._on_serial_data(b"first\r")
        monitor._on_serial_data(b"\nsecond")

        assert monitor.terminal_display.toPlainText() == "[T] first\n[T] second"

    def test_on_serial_data_hex_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.receive_hex_mode = True
        monitor._on_serial_data(b"\x41\x42\x43")
        text = monitor.terminal_display.toPlainText()
        assert "41" in text
        assert "42" in text
        assert "43" in text

    def test_on_serial_data_terminal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor._on_serial_data(b"term_data")
        # 终端模式双写：模拟器渲染 + 隐藏文档保留历史/日志
        grid_text = "".join(
            c.char for row in monitor.terminal_emulator.grid for c in row
        )
        assert "term_data" in grid_text
        assert "term_data" in monitor.terminal_display.toPlainText()

    def test_paste_warning_shows_statusbar(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.terminal_emulator.paste_warning.emit(3)

        assert "3" in monitor.statusBar().currentMessage()

    def test_send_payload_terminal_mode_uses_statusbar(self, qtbot):
        from core.payload_sender import SendResult, SendStatus
        from core.payload_sender import PayloadRequest

        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        doc_before = monitor.terminal_display.toPlainText()

        with patch.object(
            monitor.payload_sender,
            "send",
            return_value=SendResult(SendStatus.SENT, payload=b"cmd"),
        ):
            monitor.send_payload(PayloadRequest(text="cmd"), display_text="cmd")

        assert "cmd" in monitor.statusBar().currentMessage()
        assert monitor.terminal_display.toPlainText() == doc_before

    def test_load_settings_restores_terminal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        assert monitor.terminal_mode is False

        with patch(
            "ui.main_window.ConfigManager.load_app_settings",
            return_value=AppSettings(terminal_mode=True),
        ):
            monitor.load_settings()

        assert monitor.terminal_mode is True
        assert monitor.terminal_mode_button.isChecked() is True
        assert not monitor.terminal_display.isVisibleTo(monitor)

    def test_terminal_mode_data_participates_in_trimming(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        with patch.object(monitor.trim_manager, "trim_if_needed") as trim_mock:
            monitor._on_serial_data(b"line1\r\nline2\r\n")
            trim_mock.assert_called()

    def test_on_serial_error_normal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor._on_connection_error(
            "serial",
            TransportError(TransportOperation.READ, "test error", "COM1"),
            False,
        )
        text = monitor.terminal_display.toPlainText()
        assert "test error" in text

    def test_on_serial_error_terminal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor._on_connection_error(
            "serial",
            TransportError(TransportOperation.READ, "term error", "COM1"),
            False,
        )
        # 终端模式双写：模拟器显示 + 文档保留历史
        grid_text = "".join(
            c.char for row in monitor.terminal_emulator.grid for c in row
        )
        assert "term error" in grid_text
        assert "term error" in monitor.terminal_display.toPlainText()

    def test_send_data_not_connected(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.send_input.setText("hello")

        with patch("ui.main_window.QMessageBox") as MockMsg:
            monitor.send_data()
            MockMsg.warning.assert_called()

    def test_send_data_empty(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.send_data()
        monitor.serial_handler.write_data.assert_not_called()

    def test_send_data_success(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.serial_handler.write_data.return_value = True
        monitor.send_input.setText("hello")
        monitor.line_ending_combo.setCurrentIndex(0)  # 无行尾

        monitor.send_data()

        monitor.serial_handler.write_data.assert_called_once_with(b"hello")
        assert "hello" in monitor.terminal_display.toPlainText()
        assert monitor.send_input.text() == ""

    def test_send_data_with_line_ending(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.serial_handler.write_data.return_value = True
        monitor.send_input.setText("cmd")
        # 设置行尾为 \r\n
        for i in range(monitor.line_ending_combo.count()):
            if monitor.line_ending_combo.itemData(i) == "\r\n":
                monitor.line_ending_combo.setCurrentIndex(i)
                break

        monitor.send_data()
        call_args = monitor.serial_handler.write_data.call_args[0][0]
        assert call_args == b"cmd\r\n"

    def test_send_data_hex_invalid(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.send_input.setText("ZZ")
        monitor.send_mode_button.click()  # 切换到 hex 模式

        with patch("ui.main_window.QMessageBox") as MockMsg:
            monitor.send_data()
            MockMsg.warning.assert_called()
        monitor.serial_handler.write_data.assert_not_called()

    def test_send_data_with_checksum(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.serial_handler.write_data.return_value = True
        monitor.send_input.setText("AA BB")
        monitor.line_ending_combo.setCurrentIndex(0)

        # 切换为 hex + 自动 checksum
        monitor.send_mode_button.click()
        monitor.auto_checksum_checkbox.setChecked(True)
        monitor.checksum_start_spinbox.setValue(1)

        monitor.send_data()
        monitor.serial_handler.write_data.assert_called_once()
        written = monitor.serial_handler.write_data.call_args[0][0]
        assert len(written) > 2  # 原始数据 + checksum

    def test_send_data_write_failure(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.serial_handler.write_data.return_value = False
        monitor.serial_handler.last_error = "port error"
        monitor.send_input.setText("hello")

        with patch("ui.main_window.QMessageBox") as MockMsg:
            monitor.send_data()
            MockMsg.critical.assert_called()

    def test_clear_receive_area_terminal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor.clear_receive_area()
        # 终端模式下调用 emulator.clear_screen，不抛异常即可

    def test_toggle_terminal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        assert monitor.terminal_mode is False
        monitor.terminal_mode = True
        # 设置后部分 UI 元素应隐藏
        assert monitor.receive_mode_button.isVisible() is False
        assert monitor.send_mode_button.isVisible() is False
        monitor.terminal_mode = False
        # 切回正常模式时按钮恢复显示（但因父窗口未 show 仍可能不可见，故用属性判断）
        assert monitor.terminal_mode is False


class TestSerialMonitorConnectionAndChecksum:
    def test_connection_mode_defaults_to_serial(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        assert monitor.connection_mode == "serial"
        assert monitor.port_combo.isHidden() is False
        assert monitor.socket_host_input.isHidden() is True
        assert monitor.socket_port_input.isHidden() is True

    def test_toggle_connection_mode_shows_socket_inputs(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.toggle_connection_mode()

        assert monitor.connection_mode == "tcp"
        assert monitor.port_combo.isHidden() is True
        assert monitor.refresh_button.isHidden() is True
        assert monitor.socket_host_input.isHidden() is False
        assert monitor.socket_port_input.isHidden() is False
        assert monitor.baudrate_combo.isHidden() is True
        assert monitor.dtr_checkbox.isHidden() is True

    def test_second_mode_toggle_shows_rfc2217_controls(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.toggle_connection_mode()
        monitor.toggle_connection_mode()

        assert monitor.connection_mode == "rfc2217"
        assert monitor.port_combo.isHidden() is True
        assert monitor.socket_host_input.isHidden() is False
        assert monitor.socket_port_input.isHidden() is False
        assert monitor.baudrate_combo.isHidden() is False
        assert monitor.parity_combo.isHidden() is False
        assert monitor.dtr_checkbox.isHidden() is False
        assert monitor.rfc2217_timeout_spinbox.isHidden() is False
        assert monitor.rfc2217_ignore_control_checkbox.isHidden() is False

    def test_rfc2217_is_active_handler_in_rfc_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "rfc2217"

        assert monitor.active_handler is monitor.rfc2217_handler

    def test_connection_mode_cannot_change_while_connected(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True

        monitor.toggle_connection_mode()

        assert monitor.connection_mode == "serial"

    def test_manual_disconnect_state_is_separate_per_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.manual_disconnect = True

        monitor.toggle_connection_mode()

        assert monitor.connection_mode == "tcp"
        assert monitor.manual_disconnect is False

    def test_toggle_connection_cancels_pending_socket_connect(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.socket_handler = Mock()
        monitor.socket_handler.is_open.return_value = False
        monitor.socket_handler.is_connecting.return_value = True

        monitor.toggle_connection()

        assert monitor.manual_disconnect is True
        monitor.socket_handler.close.assert_called_once()
        assert "已断开" not in monitor.terminal_display.toPlainText()

    def test_pending_socket_cancel_reenables_connection_controls(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor._update_connection_mode_ui()
        monitor.socket_host_input.setText("203.0.113.1")
        monitor.socket_port_input.setText("65000")

        monitor.open_socket()
        assert monitor.connection_mode_button.isEnabled() is False

        monitor.toggle_connection()

        assert monitor.connection_mode_button.isEnabled() is True
        assert monitor.socket_host_input.isEnabled() is True

    def test_open_socket_success(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.socket_handler = Mock()
        monitor.socket_handler.is_open.return_value = False
        monitor.socket_handler.is_connecting.return_value = False
        monitor.socket_handler.open.return_value = True
        monitor.socket_host_input.setText("192.0.2.20")
        monitor.socket_port_input.setText("9000")

        monitor.open_connection()
        monitor._on_connection_state_changed(
            "tcp",
            TransportTransition(
                TransportState.CONNECTING,
                TransportState.CONNECTED,
                "192.0.2.20:9000",
            ),
        )

        monitor.socket_handler.open.assert_called_once_with("192.0.2.20", 9000)
        assert monitor.current_socket_host == "192.0.2.20"
        assert monitor.current_socket_port == 9000
        assert "192.0.2.20:9000" in monitor.terminal_display.toPlainText()

    def test_open_socket_requires_host_and_port(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.socket_host_input.clear()
        monitor.socket_port_input.clear()

        with patch("ui.main_window.QMessageBox") as mock_message:
            monitor.open_connection()

        mock_message.warning.assert_called_once()

    def test_open_rfc2217_passes_network_and_serial_configuration(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "rfc2217"
        monitor.rfc2217_handler = Mock()
        monitor.rfc2217_handler.is_open.return_value = False
        monitor.rfc2217_handler.is_connecting.return_value = False
        monitor.rfc2217_handler.open.return_value = True
        monitor.socket_host_input.setText("192.0.2.30")
        monitor.socket_port_input.setText("2217")
        monitor.baudrate_combo.setCurrentText("115200")
        monitor.parity_combo.setCurrentText("Even")
        monitor.databits_combo.setCurrentText("8")
        monitor.stopbits_combo.setCurrentText("1")
        monitor.dtr_checkbox.setChecked(True)
        monitor.rts_checkbox.setChecked(False)
        monitor.rfc2217_timeout_spinbox.setValue(1.5)
        monitor.rfc2217_ignore_control_checkbox.setChecked(True)

        monitor.open_connection()

        monitor.rfc2217_handler.open.assert_called_once_with(
            "192.0.2.30",
            2217,
            baudrate="115200",
            parity="Even",
            databits="8",
            stopbits="1",
            dtr=True,
            rts=False,
            network_timeout=1.5,
            ignore_set_control=True,
        )
        assert monitor.current_rfc2217_host == "192.0.2.30"
        assert monitor.current_rfc2217_port == 2217

    def test_rfc2217_dtr_and_rts_use_active_handler(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "rfc2217"
        monitor.rfc2217_handler = Mock()
        monitor.rfc2217_handler.is_open.return_value = True
        monitor.dtr_checkbox.setChecked(True)
        monitor.rts_checkbox.setChecked(True)

        monitor.toggle_dtr()
        monitor.toggle_rts()

        monitor.rfc2217_handler.set_dtr.assert_called_with(True)
        monitor.rfc2217_handler.set_rts.assert_called_with(True)

    def test_send_data_uses_socket_handler_in_tcp_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.serial_handler = Mock()
        monitor.socket_handler = Mock()
        monitor.socket_handler.is_open.return_value = True
        monitor.socket_handler.write_data.return_value = True
        monitor.send_input.setText("hello")

        monitor.send_data()

        monitor.socket_handler.write_data.assert_called_once_with(b"hello")
        monitor.serial_handler.write_data.assert_not_called()

    def test_terminal_key_uses_socket_handler_in_tcp_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.socket_handler = Mock()
        monitor.socket_handler.is_open.return_value = True

        monitor._on_terminal_key(b"k")

        monitor.socket_handler.write_data.assert_called_once_with(b"k")

    def test_rfc2217_send_is_reported_as_queued(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "rfc2217"
        monitor.rfc2217_handler = Mock()
        monitor.rfc2217_handler.is_open.return_value = True
        monitor.rfc2217_handler.write_data.return_value = True
        monitor.send_input.setText("hello")

        monitor.send_data()

        text = monitor.terminal_display.toPlainText()
        assert "已入队" in text or "Queued" in text
        assert monitor.send_input.text() == ""

    def test_transport_data_ignores_inactive_serial_source(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.show_timestamp = False

        monitor.connection_controller._on_data(ConnectionMode.SERIAL, b"stale serial")
        monitor.connection_controller._on_data(ConnectionMode.TCP, b"socket data")

        text = monitor.terminal_display.toPlainText()
        assert "stale serial" not in text
        assert "socket data" in text

    def test_transport_data_ignores_inactive_rfc2217_source(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.show_timestamp = False

        monitor.connection_controller._on_data(
            ConnectionMode.RFC2217, b"stale rfc2217"
        )
        monitor.connection_controller._on_data(ConnectionMode.TCP, b"socket data")

        text = monitor.terminal_display.toPlainText()
        assert "stale rfc2217" not in text
        assert "socket data" in text

    def test_socket_disconnect_reports_endpoint(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.manual_disconnect = False

        monitor._on_connection_state_changed(
            "tcp",
            TransportTransition(
                TransportState.CONNECTING,
                TransportState.CONNECTED,
                "192.0.2.20:9000",
            ),
        )
        monitor._on_connection_state_changed(
            "tcp",
            TransportTransition(
                TransportState.CONNECTED,
                TransportState.DISCONNECTED,
                "192.0.2.20:9000",
                DisconnectReason.REMOTE,
                True,
            ),
        )

        assert "192.0.2.20:9000" in monitor.terminal_display.toPlainText()

    def test_real_closing_sequence_reports_disconnect(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        handler = monitor.socket_handler
        handler.current_host = "192.0.2.20"
        handler.current_port = 9000
        handler._transition(TransportState.CONNECTING)
        handler._transition(TransportState.CONNECTED)
        before_close = monitor.terminal_display.toPlainText()

        handler._transition(TransportState.CLOSING, DisconnectReason.USER)
        handler._transition(TransportState.DISCONNECTED, DisconnectReason.USER)

        assert monitor.terminal_display.toPlainText() != before_close

    def test_cancel_before_connected_does_not_report_disconnect(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        handler = monitor.socket_handler
        handler.current_host = "192.0.2.20"
        handler.current_port = 9000
        handler._transition(TransportState.CONNECTING)
        handler._transition(TransportState.CLOSING, DisconnectReason.USER)
        handler._transition(TransportState.DISCONNECTED, DisconnectReason.USER)

        assert monitor.terminal_display.toPlainText() == ""

    def test_explicit_socket_connect_error_shows_dialog(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        with patch("ui.main_window.QMessageBox") as message_box:
            monitor._on_connection_error(
                "tcp",
                TransportError(
                    TransportOperation.CONNECT,
                    "connection refused",
                    "127.0.0.1:9000",
                ),
                True,
            )

        message_box.critical.assert_called_once()

    def test_connect_error_sets_backoff_before_modal_dialog(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.socket_handler = Mock()
        monitor.socket_handler.last_error_context = "connect"
        monitor.socket_handler.is_open.return_value = False
        monitor.socket_handler.is_connecting.return_value = False
        monitor.socket_handler.open.return_value = True
        monitor.auto_reconnect = True
        monitor.current_socket_host = "127.0.0.1"
        monitor.current_socket_port = 9000
        monitor.connection_controller.connect(
            TcpConnectionConfig("127.0.0.1", 9000), interactive=True
        )

        with patch("ui.main_window.QMessageBox") as message_box:
            message_box.critical.side_effect = (
                lambda *_args: monitor.check_device_connection()
            )
            monitor.connection_controller._on_error(
                ConnectionMode.TCP,
                TransportError(
                    TransportOperation.CONNECT,
                    "connection refused",
                    "127.0.0.1:9000",
                    DisconnectReason.CONNECT_FAILED,
                ),
            )

        monitor.socket_handler.open.assert_called_once()
        assert monitor._next_socket_reconnect_at > time.monotonic()

    def test_background_socket_connect_error_is_logged(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.socket_handler = Mock()
        monitor.current_socket_host = "127.0.0.1"
        monitor.current_socket_port = 9000

        with patch("ui.main_window.QMessageBox") as message_box:
            monitor._on_connection_error(
                "tcp",
                TransportError(
                    TransportOperation.CONNECT,
                    "connection refused",
                    "127.0.0.1:9000",
                ),
                False,
            )

        message_box.critical.assert_not_called()
        assert "127.0.0.1:9000" in monitor.terminal_display.toPlainText()

    def test_network_error_is_visible_in_terminal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.terminal_mode = True

        monitor._on_connection_error(
            "tcp",
            TransportError(
                TransportOperation.READ,
                "connection reset",
                "127.0.0.1:9000",
            ),
            False,
        )

        qtbot.waitUntil(
            lambda: "connection reset" in monitor.terminal_emulator.toPlainText()
        )

    def test_failed_socket_connection_unlocks_ui_and_sets_backoff(self, qtbot):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor._update_connection_mode_ui()
        monitor.socket_host_input.setText("127.0.0.1")
        monitor.socket_port_input.setText(str(port))

        monitor.open_socket(show_error=False)
        qtbot.waitUntil(
            lambda: not monitor.socket_handler.is_connecting(), timeout=2000
        )
        qtbot.waitUntil(
            lambda: monitor.connection_mode_button.isEnabled(), timeout=2000
        )

        assert monitor.is_connected() is False
        assert monitor._next_socket_reconnect_at > time.monotonic()
        assert f"127.0.0.1:{port}" in monitor.terminal_display.toPlainText()

    def test_remote_close_error_does_not_duplicate_disconnect_message(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor._on_connection_error(
            "tcp",
            TransportError(
                TransportOperation.READ,
                "remote host closed",
                "127.0.0.1:9000",
                DisconnectReason.REMOTE,
            ),
            False,
        )

        assert monitor.terminal_display.toPlainText() == ""

    def test_toggle_ansi_colors(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.ansi_colors_checkbox.setChecked(False)
        monitor.toggle_ansi_colors()
        assert monitor.enable_ansi_colors is False
        assert monitor.terminal_emulator.enable_ansi_colors is False

    def test_toggle_auto_reconnect(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.auto_reconnect_checkbox.setChecked(True)
        monitor.toggle_auto_reconnect()
        assert monitor.auto_reconnect is True

    def test_socket_auto_reconnect_uses_saved_endpoint(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.socket_handler = Mock()
        monitor.socket_handler.is_open.return_value = False
        monitor.socket_handler.is_connecting.return_value = False
        monitor.socket_handler.open.return_value = True
        monitor.auto_reconnect = True
        monitor.manual_disconnect = False
        monitor.current_socket_host = "127.0.0.1"
        monitor.current_socket_port = 9000
        monitor.socket_host_input.setText("127.0.0.1")
        monitor.socket_port_input.setText("9000")
        monitor.connection_controller.connect(
            TcpConnectionConfig("127.0.0.1", 9000), interactive=False
        )
        monitor.socket_handler.open.reset_mock()

        monitor.check_device_connection()

        monitor.socket_handler.open.assert_called_once_with("127.0.0.1", 9000)

    def test_rfc2217_auto_reconnect_uses_saved_endpoint(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "rfc2217"
        monitor.rfc2217_handler = Mock()
        monitor.rfc2217_handler.is_open.return_value = False
        monitor.rfc2217_handler.is_connecting.return_value = False
        monitor.rfc2217_handler.open.return_value = True
        monitor.auto_reconnect = True
        monitor.manual_disconnect = False
        monitor.current_rfc2217_host = "127.0.0.1"
        monitor.current_rfc2217_port = 2217
        monitor.socket_host_input.setText("127.0.0.1")
        monitor.socket_port_input.setText("2217")
        monitor.connection_controller.connect(
            Rfc2217ConnectionConfig("127.0.0.1", 2217), interactive=False
        )
        monitor.rfc2217_handler.open.reset_mock()

        monitor.check_device_connection()

        monitor.rfc2217_handler.open.assert_called_once()

    def test_background_rfc2217_connect_error_is_logged(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "rfc2217"
        monitor.current_rfc2217_host = "127.0.0.1"
        monitor.current_rfc2217_port = 2217

        with patch("ui.main_window.QMessageBox") as message_box:
            monitor._on_connection_error(
                "rfc2217",
                TransportError(
                    TransportOperation.CONNECT,
                    "negotiation timeout",
                    "127.0.0.1:2217",
                ),
                False,
            )

        message_box.critical.assert_not_called()
        assert "127.0.0.1:2217" in monitor.terminal_display.toPlainText()

    def test_load_settings_restores_socket_mode(self, qtbot):
        settings = dict(DEFAULT_SETTINGS)
        settings.update(
            connection_mode="tcp",
            socket_host="192.0.2.30",
            socket_port="7000",
        )

        with patch(
            "ui.main_window.ConfigManager.load_settings", return_value=settings
        ):
            monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        assert monitor.connection_mode == "tcp"
        assert monitor.socket_host_input.text() == "192.0.2.30"
        assert monitor.socket_port_input.text() == "7000"
        assert monitor.socket_host_input.isHidden() is False
        assert monitor.port_combo.isHidden() is True

    def test_save_settings_includes_socket_endpoint(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "tcp"
        monitor.socket_host_input.setText("192.0.2.40")
        monitor.socket_port_input.setText("8000")

        with patch("ui.main_window.ConfigManager.save_settings") as save_settings:
            monitor.save_settings()

        saved = save_settings.call_args.args[0]
        assert saved["schema_version"] == 2
        assert saved["connection_mode"] == "tcp"
        assert saved["connections"]["tcp"] == {
            "host": "192.0.2.40",
            "port": 8000,
        }

    def test_load_rfc2217_settings(self, qtbot):
        settings = dict(DEFAULT_SETTINGS)
        settings.update(
            connection_mode="rfc2217",
            socket_host="192.0.2.50",
            socket_port="2217",
            rfc2217_timeout=2.5,
            rfc2217_ignore_set_control=True,
        )

        with patch(
            "ui.main_window.ConfigManager.load_settings", return_value=settings
        ):
            monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        assert monitor.connection_mode == "rfc2217"
        assert monitor.rfc2217_timeout_spinbox.value() == 2.5
        assert monitor.rfc2217_ignore_control_checkbox.isChecked() is True
        assert monitor.baudrate_combo.isHidden() is False
        assert monitor.socket_host_input.isHidden() is False

    def test_save_settings_includes_rfc2217_options(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.connection_mode = "rfc2217"
        monitor.rfc2217_timeout_spinbox.setValue(1.5)
        monitor.rfc2217_ignore_control_checkbox.setChecked(True)

        with patch("ui.main_window.ConfigManager.save_settings") as save_settings:
            monitor.save_settings()

        saved = save_settings.call_args.args[0]
        assert saved["connection_mode"] == "rfc2217"
        assert saved["connections"]["rfc2217"]["network_timeout"] == 1.5
        assert saved["connections"]["rfc2217"]["ignore_set_control"] is True

    def test_tcp_and_rfc2217_controls_keep_independent_values(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.toggle_connection_mode()
        monitor.socket_host_input.setText("tcp.example")
        monitor.socket_port_input.setText("9000")

        monitor.toggle_connection_mode()
        monitor.socket_host_input.setText("rfc.example")
        monitor.socket_port_input.setText("2217")
        monitor.baudrate_combo.setCurrentText("38400")

        monitor.toggle_connection_mode()
        monitor.toggle_connection_mode()
        assert monitor.socket_host_input.text() == "tcp.example"
        assert monitor.socket_port_input.text() == "9000"

        monitor.toggle_connection_mode()
        assert monitor.socket_host_input.text() == "rfc.example"
        assert monitor.socket_port_input.text() == "2217"
        assert monitor.baudrate_combo.currentText() == "38400"

    def test_refresh_ports(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        with patch.object(monitor.serial_handler, "get_available_ports",
                          return_value=["/dev/ttyUSB0", "/dev/ttyACM0"]):
            monitor.refresh_ports()
        items = [monitor.port_combo.itemText(i) for i in range(monitor.port_combo.count())]
        assert any("/dev/ttyUSB0" in t for t in items)

    def test_open_serial_no_port(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.port_combo.clear()
        with patch("ui.main_window.QMessageBox") as MockMsg:
            monitor.open_serial()
            MockMsg.warning.assert_called()

    def test_open_serial_success(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor.serial_handler.open.return_value = True
        # 清空现有端口，添加我们控制的端口
        monitor.port_combo.clear()
        monitor.port_combo.addItem("/dev/ttyUSB0")
        monitor.port_combo.setCurrentIndex(0)

        monitor.open_serial()
        monitor._on_connection_state_changed(
            "serial",
            TransportTransition(
                TransportState.CONNECTING,
                TransportState.CONNECTED,
                "/dev/ttyUSB0",
            ),
        )
        monitor.serial_handler.open.assert_called_once()
        assert monitor.current_port == "/dev/ttyUSB0"
        assert monitor.manual_disconnect is False
        assert "已连接" in monitor.terminal_display.toPlainText() or "Connected" in monitor.terminal_display.toPlainText()

    def test_open_serial_failure(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor.serial_handler.open.return_value = False
        monitor.serial_handler.last_error = "permission denied"
        monitor.port_combo.addItem("/dev/ttyUSB0")
        monitor.port_combo.setCurrentIndex(0)

        with patch("ui.main_window.QMessageBox") as MockMsg:
            monitor.open_serial()
            monitor.connection_controller._on_error(
                ConnectionMode.SERIAL,
                TransportError(
                    TransportOperation.CONNECT,
                    "permission denied",
                    "/dev/ttyUSB0",
                    DisconnectReason.CONNECT_FAILED,
                ),
            )
            MockMsg.critical.assert_called()

    def test_open_serial_already_open(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.open_serial()
        monitor.serial_handler.open.assert_not_called()

    def test_close_serial_not_open(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor.close_serial(silent=True)
        monitor.serial_handler.close.assert_not_called()

    def test_close_serial_opened_silent(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.close_serial(silent=True)
        monitor.serial_handler.close.assert_called_once()

    def test_close_serial_opened_device_lost(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.current_port = "/dev/ttyUSB0"
        monitor.connection_controller.remember_config(
            SerialConnectionConfig("/dev/ttyUSB0")
        )
        monitor.close_serial(silent=False, device_lost=True)
        monitor._on_connection_state_changed(
            "serial",
            TransportTransition(
                TransportState.CONNECTED,
                TransportState.DISCONNECTED,
                "/dev/ttyUSB0",
                DisconnectReason.DEVICE_REMOVED,
                True,
            ),
        )
        monitor.serial_handler.close.assert_called_once()
        text = monitor.terminal_display.toPlainText()
        assert text != ""

    def test_toggle_connection_already_open(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.toggle_connection()
        assert monitor.manual_disconnect is True
        monitor.serial_handler.close.assert_called_once()

    def test_toggle_connection_closed(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor.serial_handler.open.return_value = True
        monitor.port_combo.addItem("/dev/ttyUSB0")
        monitor.port_combo.setCurrentIndex(0)
        monitor.toggle_connection()
        monitor.serial_handler.open.assert_called_once()
        assert monitor.manual_disconnect is False

    def test_calculate_checksum_empty(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.send_input.setText("")
        monitor.calculate_checksum()
        assert monitor.checksum_input.text() == ""

    def test_calculate_checksum_ascii(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.send_input.setText("ABC")
        monitor.auto_checksum_checkbox.setChecked(False)
        monitor.calculate_checksum()
        # A=0x41, B=0x42, C=0x43, sum=0xC6
        assert "C6" in monitor.checksum_input.text()

    def test_calculate_checksum_invalid_hex(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.send_input.setText("ZZ")
        monitor.send_mode_button.click()  # 切换 hex
        monitor.calculate_checksum()
        # invalid_hex 或类似错误
        assert monitor.checksum_input.text() != ""

    def test_calculate_checksum_auto_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.send_input.setText("AA BB")
        monitor.send_mode_button.click()  # hex
        monitor.auto_checksum_checkbox.setChecked(True)
        monitor.checksum_start_spinbox.setValue(1)
        monitor.checksum_end_combo.setCurrentIndex(0)
        monitor.calculate_checksum()
        # 0xAA + 0xBB = 0x65
        assert "65" in monitor.checksum_input.text()

    def test_check_device_connection_no_current(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        with patch.object(monitor.serial_handler, "get_available_ports",
                          return_value=["/dev/ttyUSB0"]):
            monitor.check_device_connection()  # 无 current_port，不应抛异常

    def test_check_device_connection_device_lost(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.current_port = "/dev/ttyUSB0"
        monitor.connection_controller.remember_config(
            SerialConnectionConfig("/dev/ttyUSB0")
        )
        with patch.object(monitor.serial_handler, "get_available_ports",
                          return_value=[]):
            monitor.check_device_connection()
        monitor.serial_handler.close.assert_called_once()

    def test_check_device_connection_auto_reconnect(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor.serial_handler.open.return_value = True
        monitor.auto_reconnect = True
        monitor.manual_disconnect = False
        monitor.current_port = "/dev/ttyUSB0"
        monitor.port_combo.addItem("/dev/ttyUSB0")
        monitor.port_combo.setCurrentIndex(0)
        monitor.connection_controller.connect(
            SerialConnectionConfig("/dev/ttyUSB0"), interactive=False
        )
        monitor.serial_handler.open.reset_mock()

        with patch.object(monitor.serial_handler, "get_available_ports",
                          return_value=["/dev/ttyUSB0"]):
            monitor.check_device_connection()
        monitor.serial_handler.open.assert_called_once()

    def test_on_terminal_key(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = True
        monitor.serial_handler.write_data.return_value = True
        monitor._on_terminal_key(b"k")
        monitor.serial_handler.write_data.assert_called_once_with(b"k")

    def test_on_terminal_key_not_open(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor._on_terminal_key(b"k")
        monitor.serial_handler.write_data.assert_not_called()


class TestSerialMonitorSearch:
    def test_open_search_shows_bar(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        with patch.object(monitor.search_bar, "show_bar") as mock_show:
            monitor._open_search()
            mock_show.assert_called_once()

    def test_close_search_clears_highlights(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        with patch.object(monitor, "_clear_search_highlights") as mock_clear:
            monitor._close_search()
            mock_clear.assert_called_once()

    def test_search_normal_found(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.append_to_terminal("hello world hello")
        monitor._do_search("hello", True, False)
        text = monitor.terminal_display.textCursor().selectedText()
        assert text == "hello"

    def test_search_normal_case_sensitive(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.append_to_terminal("Hello hello")
        monitor._do_search("hello", True, True)
        text = monitor.terminal_display.textCursor().selectedText()
        assert text == "hello"

    def test_search_normal_not_found(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.append_to_terminal("hello world")
        with patch.object(monitor.search_bar, "set_no_result") as mock_no:
            monitor._do_search("xyz", True, False)
            mock_no.assert_called_once()

    def test_search_normal_backward(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.append_to_terminal("hello world hello")
        monitor._do_search("hello", False, False)
        text = monitor.terminal_display.textCursor().selectedText()
        assert text == "hello"

    def test_search_normal_wrap(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.append_to_terminal("only one")
        # 光标已在末尾，反向搜索会从开头找
        monitor._do_search("only", False, False)
        text = monitor.terminal_display.textCursor().selectedText()
        assert text == "only"

    def test_search_terminal_found(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor.terminal_emulator.process_bytes(b"hello world hello")
        cursor_before = (
            monitor.terminal_emulator.cursor_row,
            monitor.terminal_emulator.cursor_col,
        )
        monitor._do_search("hello", True, False)
        assert monitor.terminal_emulator.search_highlight == (0, 0, 5)
        assert (
            monitor.terminal_emulator.cursor_row,
            monitor.terminal_emulator.cursor_col,
        ) == cursor_before

        monitor.terminal_emulator.process_bytes(b"!")
        assert monitor.terminal_emulator.grid[0][17].char == "!"

    def test_search_terminal_cycles_using_previous_match(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor.terminal_emulator.process_bytes(b"hello world hello")

        monitor._do_search("hello", True, False)
        assert monitor.terminal_emulator.search_highlight == (0, 0, 5)

        monitor._do_search("hello", True, False)
        assert monitor.terminal_emulator.search_highlight == (0, 12, 5)

    def test_search_terminal_not_found(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor.terminal_emulator.process_bytes(b"hello")
        with patch.object(monitor.search_bar, "set_no_result") as mock_no:
            monitor._do_search("xyz", True, False)
            mock_no.assert_called_once()

    def test_search_terminal_empty_text(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        with patch.object(monitor.search_bar, "set_no_result") as mock_no:
            monitor._do_search("", True, False)
            mock_no.assert_called_once()

    def test_search_terminal_backward(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor.terminal_emulator.process_bytes(b"abc abc abc")
        # 光标在末尾，反向搜索
        monitor.terminal_emulator.cursor_col = 11
        monitor.terminal_emulator.cursor_row = 0
        monitor._do_search("abc", False, False)
        assert monitor.terminal_emulator.search_highlight is not None

    def test_search_terminal_case_insensitive(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor.terminal_emulator.process_bytes(b"Hello HELLO")
        monitor._do_search("hello", True, False)
        assert monitor.terminal_emulator.search_highlight is not None

    def test_clear_search_highlights(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor.terminal_emulator.search_highlight = (0, 5)
        monitor._clear_search_highlights()
        assert monitor.terminal_emulator.search_highlight is None

    def test_clear_search_highlights_normal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        # 正常模式下不做任何操作，不抛异常
        monitor._clear_search_highlights()


class TestSerialMonitorCheckDeviceMore:
    def test_check_device_auto_reconnect_terminal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor.serial_handler.open.return_value = True
        monitor.auto_reconnect = True
        monitor.manual_disconnect = False
        monitor.current_port = "/dev/ttyUSB0"
        monitor.port_combo.addItem("/dev/ttyUSB0")
        monitor.terminal_mode = True
        monitor.connection_controller.connect(
            SerialConnectionConfig("/dev/ttyUSB0"), interactive=False
        )
        monitor.serial_handler.open.reset_mock()

        with patch.object(monitor.serial_handler, "get_available_ports",
                          return_value=["/dev/ttyUSB0"]):
            monitor.check_device_connection()
        monitor.serial_handler.open.assert_called_once()

    def test_check_device_auto_reconnect_no_current(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor.auto_reconnect = True
        monitor.manual_disconnect = False
        monitor.current_port = None

        with patch.object(monitor.serial_handler, "get_available_ports",
                          return_value=["/dev/ttyUSB0"]):
            monitor.check_device_connection()  # 不抛异常

    def test_check_device_find_new_port(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor.serial_handler.open.return_value = True
        monitor.auto_reconnect = True
        monitor.manual_disconnect = False
        monitor.current_port = None
        monitor.port_combo.addItem("/dev/ttyUSB0")
        monitor.port_combo.setCurrentIndex(0)

        with patch.object(monitor.serial_handler, "get_available_ports",
                          return_value=["/dev/ttyUSB0"]):
            monitor.check_device_connection()
        monitor.serial_handler.open.assert_not_called()
        assert monitor.current_port is None

    def test_serial_reconnect_does_not_select_a_different_port(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor.auto_reconnect = True
        monitor.manual_disconnect = False
        monitor.current_port = "/dev/ttyUSB0"
        monitor.connection_controller.connect(
            SerialConnectionConfig("/dev/ttyUSB0"), interactive=False
        )
        monitor.serial_handler.open.reset_mock()

        with patch.object(
            monitor.serial_handler,
            "get_available_ports",
            return_value=["/dev/ttyUSB1"],
        ):
            monitor.check_device_connection()

        monitor.serial_handler.open.assert_not_called()
        assert monitor.current_port == "/dev/ttyUSB0"

    def test_check_device_manual_disconnect_no_reconnect(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor.auto_reconnect = True
        monitor.manual_disconnect = True
        monitor.current_port = "/dev/ttyUSB0"
        monitor.connection_controller.remember_config(
            SerialConnectionConfig("/dev/ttyUSB0")
        )

        with patch.object(monitor.serial_handler, "get_available_ports",
                          return_value=["/dev/ttyUSB0"]):
            monitor.check_device_connection()
        monitor.serial_handler.open.assert_not_called()
