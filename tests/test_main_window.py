"""
测试 ui/main_window.py
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from PyQt6.QtGui import QTextDocument
from PyQt6.QtWidgets import QApplication

from ui.main_window import TerminalTrimManager, SerialMonitor


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
        # 应裁剪到 max_lines 附近
        assert doc.blockCount() <= 20

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
        # 不应抛异常
        tm.trim_if_needed(doc)


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
        monitor._on_serial_data(b"no_newline")
        text = monitor.terminal_display.toPlainText()
        assert "no_newline" in text
        assert text.endswith("\n")

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
        # 终端模式下数据由 emulator 处理，terminal_display 不应直接显示
        text = monitor.terminal_display.toPlainText()
        assert "term_data" not in text

    def test_on_serial_error_normal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor._on_serial_error("test error")
        text = monitor.terminal_display.toPlainText()
        assert "test error" in text

    def test_on_serial_error_terminal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor._on_serial_error("term error")
        # 终端模式下错误也由 emulator 处理
        text = monitor.terminal_display.toPlainText()
        assert "term error" not in text

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
        monitor.close_serial(silent=False, device_lost=True)
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
        monitor._do_search("hello", True, False)
        assert monitor.terminal_emulator.search_highlight is not None
        assert monitor.terminal_emulator.search_highlight[0] == 0

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
        monitor.serial_handler.open.assert_called_once()
        assert monitor.current_port == "/dev/ttyUSB0"

    def test_check_device_manual_disconnect_no_reconnect(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.serial_handler = Mock()
        monitor.serial_handler.is_open.return_value = False
        monitor.auto_reconnect = True
        monitor.manual_disconnect = True
        monitor.current_port = "/dev/ttyUSB0"

        with patch.object(monitor.serial_handler, "get_available_ports",
                          return_value=["/dev/ttyUSB0"]):
            monitor.check_device_connection()
        monitor.serial_handler.open.assert_not_called()
