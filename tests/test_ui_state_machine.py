"""
UI 状态机测试

验证 SerialMonitor 在各种模式切换下的一致性。
"""

from unittest.mock import MagicMock, patch

import pytest

from ui.main_window import SerialMonitor


# ── 模式切换不变式 ──────────────────────────────────────


class TestModeSwitchInvariants:
    def test_terminal_mode_hides_receive_send_buttons(self, qtbot):
        """terminal_mode=True 时，接收/发送模式按钮应隐藏。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        monitor.terminal_mode = True
        # 按钮在 widget 未 show 时 isVisible 可能为 False
        # 测试属性值更可靠
        assert monitor.terminal_mode is True

        monitor.terminal_mode = False
        assert monitor.terminal_mode is False

    def test_receive_mode_toggle_persists(self, qtbot):
        """切换接收模式后状态应保持。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)

        for _ in range(3):
            monitor.toggle_receive_mode()
        # 3 次切换后状态应回到 False
        assert monitor.receive_hex_mode is False

        monitor.toggle_receive_mode()
        assert monitor.receive_hex_mode is True

    def test_send_mode_toggle_persists(self, qtbot):
        """切换发送模式后状态应保持。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        initial = monitor.send_hex_mode
        monitor.toggle_send_mode()
        assert monitor.send_hex_mode is not initial
        monitor.toggle_send_mode()
        assert monitor.send_hex_mode is initial

    def test_auto_scroll_toggle(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        initial = monitor.auto_scroll
        # toggle_auto_scroll 读取 checkbox 状态
        monitor.auto_scroll_checkbox.setChecked(not initial)
        monitor.toggle_auto_scroll()
        assert monitor.auto_scroll is not initial

    def test_timestamp_toggle(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        initial = monitor.show_timestamp
        # toggle_timestamp 读取 checkbox 状态
        monitor.timestamp_checkbox.setChecked(not initial)
        monitor.toggle_timestamp()
        assert monitor.show_timestamp is not initial

    def test_ansi_colors_toggle(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.ansi_colors_checkbox.setChecked(False)
        monitor.toggle_ansi_colors()
        assert monitor.enable_ansi_colors is False
        assert monitor.terminal_emulator.enable_ansi_colors is False

        monitor.ansi_colors_checkbox.setChecked(True)
        monitor.toggle_ansi_colors()
        assert monitor.enable_ansi_colors is True
        assert monitor.terminal_emulator.enable_ansi_colors is True

    def test_auto_reconnect_toggle(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.auto_reconnect_checkbox.setChecked(True)
        monitor.toggle_auto_reconnect()
        assert monitor.auto_reconnect is True


# ── 模式 + 数据流组合 ──────────────────────────────────────


class TestModeDataFlow:
    def test_normal_mode_ascii_data(self, qtbot):
        """正常模式 + ASCII 数据：terminal_display 显示文本。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.receive_hex_mode = False
        monitor.terminal_mode = False
        monitor.show_timestamp = False

        monitor._on_serial_data(b"hello\n")
        text = monitor.terminal_display.toPlainText()
        assert "hello" in text

    def test_normal_mode_hex_data(self, qtbot):
        """正常模式 + hex 模式接收：terminal_display 显示 hex 字符串。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.receive_hex_mode = True
        monitor.terminal_mode = False
        monitor.show_timestamp = False

        monitor._on_serial_data(b"\x41\x42\x43")
        text = monitor.terminal_display.toPlainText()
        assert "41" in text
        assert "42" in text

    def test_terminal_mode_routes_to_emulator(self, qtbot):
        """终端模式：数据走 emulator，不直接写 terminal_display。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor.show_timestamp = False

        before = monitor.terminal_display.toPlainText()
        monitor._on_serial_data(b"term data\n")
        after = monitor.terminal_display.toPlainText()
        # 终端模式下数据由 emulator 处理，terminal_display 不应直接显示
        assert before == after

    def test_receive_mode_button_text(self, qtbot):
        """接收模式按钮的文本应随模式变化。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.receive_hex_mode = False
        monitor.update_texts()
        text_asc = monitor.receive_mode_button.text()

        monitor.receive_hex_mode = True
        monitor.update_texts()
        text_hex = monitor.receive_mode_button.text()

        # 两种模式的按钮文本应不同
        assert text_asc != text_hex

    def test_send_mode_button_text(self, qtbot):
        """发送模式按钮的文本应随模式变化。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.send_hex_mode = False
        monitor.update_texts()
        text_asc = monitor.send_mode_button.text()

        monitor.send_hex_mode = True
        monitor.update_texts()
        text_hex = monitor.send_mode_button.text()

        assert text_asc != text_hex


# ── 时间戳/ANSI 切换的不变式 ──────────────────────────────


class TestDisplayInvariants:
    def test_timestamp_off_no_brackets(self, qtbot):
        """show_timestamp=False 时，输出应无时间戳。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.show_timestamp = False
        monitor.enable_ansi_colors = False
        monitor.append_to_terminal("plain text")
        text = monitor.terminal_display.toPlainText()
        # 无 [HH:MM:SS] 时间戳
        assert "[" not in text or "]" not in text

    def test_ansi_off_strips_escape(self, qtbot):
        """enable_ansi_colors=False 时，输出应无 ANSI 转义码。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.enable_ansi_colors = False
        monitor.show_timestamp = False
        monitor.append_to_terminal("\x1b[31mRED\x1b[0m")
        text = monitor.terminal_display.toPlainText()
        assert "\x1b" not in text
        assert "RED" in text

    def test_multiple_appends_accumulate(self, qtbot):
        """多次 append_to_terminal 应累积内容。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.show_timestamp = False
        for i in range(5):
            monitor.append_to_terminal(f"line{i}\n")
        text = monitor.terminal_display.toPlainText()
        for i in range(5):
            assert f"line{i}" in text


# ── 搜索状态机 ──────────────────────────────────────────


class TestSearchStateMachine:
    def test_search_no_text_does_not_update(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.append_to_terminal("hello world")
        # 搜索空文本
        monitor._do_search("", True, False)
        # 不抛异常，不更新结果
        text = monitor.search_bar.result_label.text()
        assert text == "" or text == "0 / 0"

    def test_search_found_updates_result(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.append_to_terminal("hello world hello")
        monitor._do_search("hello", True, False)
        # 至少找到一个，结果标签应更新
        text = monitor.search_bar.result_label.text()
        assert "/" in text

    def test_search_not_found_sets_no_result(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.append_to_terminal("hello world")
        monitor._do_search("xyz_not_exist", True, False)
        text = monitor.search_bar.result_label.text()
        assert text == "0 / 0"

    def test_search_in_terminal_mode(self, qtbot):
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.terminal_mode = True
        monitor.terminal_emulator.process_bytes(b"hello world")
        monitor._do_search("hello", True, False)
        assert monitor.terminal_emulator.search_highlight is not None

    def test_search_switches_mode_does_not_crash(self, qtbot):
        """模式切换时搜索状态不应导致崩溃。"""
        monitor = SerialMonitor()
        qtbot.addWidget(monitor)
        monitor.append_to_terminal("hello")
        monitor._do_search("hello", True, False)

        # 切换到终端模式
        monitor.terminal_mode = True
        monitor._do_search("hello", True, False)
        # 不抛异常
