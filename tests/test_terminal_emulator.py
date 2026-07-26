"""
测试 ui/terminal_emulator.py
"""

import pytest

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QKeyEvent, QTextCursor
from PyQt6.QtWidgets import QTextEdit

from ui.terminal_emulator import TerminalEmulator, _Cell


class TestTerminalEmulatorBasic:
    def test_initial_dimensions(self, qtbot):
        term = TerminalEmulator(rows=10, cols=40)
        qtbot.addWidget(term)
        assert term.rows == 10
        assert term.cols == 40
        assert len(term.grid) == 10
        assert len(term.grid[0]) == 40
        assert term.lineWrapMode() == QTextEdit.LineWrapMode.NoWrap

    def test_clear_screen(self, qtbot):
        term = TerminalEmulator(rows=5, cols=5)
        qtbot.addWidget(term)

        term.process_bytes(b"hello")
        term.clear_screen()

        assert term.cursor_row == 0
        assert term.cursor_col == 0
        for row in term.grid:
            for cell in row:
                assert cell.char == " "

    def test_set_dimensions(self, qtbot):
        term = TerminalEmulator(rows=5, cols=5)
        qtbot.addWidget(term)

        term.set_dimensions(8, 60)
        assert term.rows == 8
        assert term.cols == 60


class TestTerminalEmulatorText:
    def test_utf8_character_split_across_chunks(self, qtbot):
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)

        encoded = "你".encode("utf-8")
        term.process_bytes(encoded[:1])
        assert term.cursor_col == 0

        term.process_bytes(encoded[1:])
        assert term.grid[0][0].char == "你"
        assert term.cursor_col == 1

    def test_process_plain_text(self, qtbot):
        term = TerminalEmulator(rows=5, cols=20)
        qtbot.addWidget(term)

        term.process_bytes(b"hello")
        assert term.grid[0][0].char == "h"
        assert term.grid[0][4].char == "o"
        assert term.cursor_col == 5

    def test_process_newline(self, qtbot):
        term = TerminalEmulator(rows=5, cols=20)
        qtbot.addWidget(term)

        term.process_bytes(b"hi\nthere")
        assert term.grid[0][0].char == "h"
        assert term.grid[0][1].char == "i"
        assert term.grid[1][2].char == "t"

    def test_process_carriage_return(self, qtbot):
        term = TerminalEmulator(rows=5, cols=20)
        qtbot.addWidget(term)

        term.process_bytes(b"hello\rworld")
        assert term.grid[0][0].char == "w"
        assert term.grid[0][4].char == "d"

    def test_process_backspace(self, qtbot):
        term = TerminalEmulator(rows=5, cols=20)
        qtbot.addWidget(term)

        term.process_bytes(b"abc\x08d")
        assert term.grid[0][1].char == "b"
        assert term.grid[0][2].char == "d"

    def test_process_tab(self, qtbot):
        term = TerminalEmulator(rows=5, cols=20)
        qtbot.addWidget(term)

        term.process_bytes(b"a\tb")
        assert term.grid[0][0].char == "a"
        assert term.grid[0][8].char == "b"

    def test_cursor_wrap(self, qtbot):
        term = TerminalEmulator(rows=5, cols=3)
        qtbot.addWidget(term)

        term.process_bytes(b"abc")
        assert term.grid[0][0].char == "a"
        assert term.grid[0][2].char == "c"
        assert term.cursor_row == 0
        assert term.cursor_col == 2

        term.process_bytes(b"d")
        assert term.grid[1][0].char == "d"

    def test_scroll_up(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"line1\r\nline2\r\nline3\r\nline4")
        assert term.grid[1][0].char == "l"
        assert term.grid[1][4].char == "3"
        assert term.grid[2][0].char == "l"
        assert term.grid[2][4].char == "4"


class TestTerminalEmulatorCSI:
    def test_csi_cursor_up(self, qtbot):
        term = TerminalEmulator(rows=5, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\n\n\x1b[2A^")
        assert term.cursor_row == 0
        assert term.grid[0][0].char == "^"

    def test_csi_cursor_down(self, qtbot):
        term = TerminalEmulator(rows=5, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[2Bv")
        assert term.cursor_row == 2
        assert term.grid[2][0].char == "v"

    def test_csi_cursor_forward(self, qtbot):
        term = TerminalEmulator(rows=5, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[3C>")
        assert term.grid[0][3].char == ">"

    def test_csi_cursor_backward(self, qtbot):
        term = TerminalEmulator(rows=5, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"    \x1b[2D<")
        assert term.grid[0][2].char == "<"

    def test_csi_cursor_position(self, qtbot):
        term = TerminalEmulator(rows=5, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[3;4H*")
        assert term.cursor_row == 2
        assert term.grid[2][3].char == "*"

    def test_csi_erase_line(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"0123456789\x1b[5D\x1b[K")
        assert term.grid[0][3].char == "3"
        assert term.grid[0][4].char == " "
        assert term.grid[0][0].char == "0"

    def test_csi_erase_display(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"hello\nworld\x1b[2Jx")
        assert term.grid[0][0].char == " "
        assert term.grid[1][9].char == "x"

    def test_csi_save_restore_cursor(self, qtbot):
        term = TerminalEmulator(rows=5, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[3;3H\x1b[s\x1b[1;1H\x1b[uX")
        assert term.grid[2][2].char == "X"

    def test_csi_sgr_color(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[31mRed")
        assert term.grid[0][0].char == "R"

    def test_csi_sgr_disabled(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)
        term.enable_ansi_colors = False

        term.process_bytes(b"\x1b[31mRed")
        assert term.grid[0][0].char == "R"

    def test_incomplete_csi_buffered(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[")
        assert term._esc_buf == "\x1b["

        term.process_bytes(b"2Jx")
        assert term._esc_buf == ""
        assert term.grid[0][0].char == "x"

    def test_dcs_control_string_ignored(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1bPignored\x1b\\OK")
        assert term.grid[0][0].char == "O"
        assert term.grid[0][1].char == "K"

    def test_osc_control_string_ignored(self, qtbot):
        term = TerminalEmulator(rows=3, cols=20)
        qtbot.addWidget(term)

        term.process_bytes(b"before\x1b]0;device-title\x07after")
        text = "".join(cell.char for cell in term.grid[0]).rstrip()
        assert text == "beforeafter"

    def test_osc_control_string_buffered_across_chunks(self, qtbot):
        term = TerminalEmulator(rows=3, cols=20)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b]0;device")
        assert term._esc_buf == "\x1b]0;device"

        term.process_bytes(b"-title\x1b\\OK")
        assert term._esc_buf == ""
        assert term.grid[0][0].char == "O"
        assert term.grid[0][1].char == "K"


class TestTerminalEmulatorKeyboard:
    def test_regular_key(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        received = []
        term.key_pressed.connect(received.append)

        qtbot.keyClick(term, "a")
        assert received == [b"a"]

    def test_enter_key(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        received = []
        term.key_pressed.connect(received.append)

        qtbot.keyClick(term, Qt.Key.Key_Return)
        assert received == [b"\r"]

    def test_backspace_key(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        received = []
        term.key_pressed.connect(received.append)

        qtbot.keyClick(term, Qt.Key.Key_Backspace)
        assert received == [b"\x7f"]

    def test_arrow_key(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        received = []
        term.key_pressed.connect(received.append)

        qtbot.keyClick(term, Qt.Key.Key_Up)
        assert received == [b"\x1b[A"]

    def test_ctrl_key(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        received = []
        term.key_pressed.connect(received.append)

        qtbot.keyClick(term, "c", modifier=Qt.KeyboardModifier.ControlModifier)
        assert received == [b"\x03"]

    def test_ctrl_shift_c_copies_without_sending_etx(self, qtbot, qapp):
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)
        term.process_bytes(b"hello")
        term._render_full()
        cursor = term.textCursor()
        cursor.setPosition(0)
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.KeepAnchor,
            5,
        )
        term.setTextCursor(cursor)
        received = []
        term.key_pressed.connect(received.append)

        qtbot.keyClick(
            term,
            Qt.Key.Key_C,
            modifier=(
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.ShiftModifier
            ),
        )

        assert received == []
        assert qapp.clipboard().text() == "hello"

    def test_ctrl_shift_v_sends_clipboard_as_utf8(self, qtbot, qapp):
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)
        qapp.clipboard().setText("你好")
        received = []
        term.key_pressed.connect(received.append)

        qtbot.keyClick(
            term,
            Qt.Key.Key_V,
            modifier=(
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.ShiftModifier
            ),
        )

        assert received == ["你好".encode("utf-8")]


class TestPasteConfirmation:
    def _paste(self, qtbot, term):
        qtbot.keyClick(
            term,
            Qt.Key.Key_V,
            modifier=(
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.ShiftModifier
            ),
        )

    def test_multiline_paste_requires_second_confirmation(self, qtbot, qapp):
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)
        qapp.clipboard().setText("AT+GMI\nAT+GMR\n")
        sent: list[bytes] = []
        warnings: list[int] = []
        term.key_pressed.connect(sent.append)
        term.paste_warning.connect(warnings.append)

        self._paste(qtbot, term)
        assert sent == []
        assert warnings == [3]

        self._paste(qtbot, term)
        assert sent == ["AT+GMI\nAT+GMR\n".encode("utf-8")]

    def test_pending_paste_expires(self, qtbot, qapp):
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)
        qapp.clipboard().setText("line1\nline2\n")
        sent: list[bytes] = []
        term.key_pressed.connect(sent.append)

        now = [1000.0]
        term._paste_clock = lambda: now[0]

        self._paste(qtbot, term)
        assert sent == []

        now[0] = 1004.0
        self._paste(qtbot, term)
        assert sent == []

    def test_changed_clipboard_resets_pending(self, qtbot, qapp):
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)
        sent: list[bytes] = []
        warnings: list[int] = []
        term.key_pressed.connect(sent.append)
        term.paste_warning.connect(warnings.append)

        qapp.clipboard().setText("a\nb\n")
        self._paste(qtbot, term)
        qapp.clipboard().setText("c\nd\n")
        self._paste(qtbot, term)

        assert sent == []
        assert len(warnings) == 2

    def test_large_single_line_requires_confirmation(self, qtbot, qapp):
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)
        qapp.clipboard().setText("x" * 2000)
        sent: list[bytes] = []
        warnings: list[int] = []
        term.key_pressed.connect(sent.append)
        term.paste_warning.connect(warnings.append)

        self._paste(qtbot, term)
        assert sent == []
        assert warnings == [1]


class TestAuditFixes:
    def test_tab_beyond_last_stop_does_not_hang(self, qtbot):
        term = TerminalEmulator(rows=5, cols=1)
        qtbot.addWidget(term)

        term.process_bytes(b"\t")

        assert term.cursor_col == 0

    def test_tab_near_right_margin_completes(self, qtbot):
        term = TerminalEmulator(rows=5, cols=80)
        qtbot.addWidget(term)

        term.process_bytes(b"x" * 72 + b"\t")

        assert term.cursor_col == 79

    def test_reverse_index_clamps_at_top(self, qtbot):
        term = TerminalEmulator(rows=10, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[3;6r\x1bM\x1bM")

        assert term.cursor_row == 0

        term.process_bytes(b"X")
        assert term.grid[0][0].char == "X"

    def test_resize_clamps_saved_cursor(self, qtbot):
        term = TerminalEmulator(rows=24, cols=80)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[20;1H\x1b7")
        term.resize_grid(10, 80)
        term.process_bytes(b"\x1b8X")

        assert 0 <= term.cursor_row < term.rows
        assert term.grid[term.cursor_row][0].char == "X"

    def test_resize_clamps_saved_cursor_columns(self, qtbot):
        term = TerminalEmulator(rows=10, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[1;10H\x1b7")
        term.resize_grid(5, 4)
        term.process_bytes(b"\x1b8X")

        assert term.grid[0][3].char == "X"
        assert 0 <= term.cursor_col < term.cols

    def test_set_dimensions_resets_scroll_region(self, qtbot):
        term = TerminalEmulator(rows=10, cols=20)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[1;10r")
        term.set_dimensions(5, 20)

        assert term._scroll_top == 0
        assert term._scroll_bottom == 4

        term.process_bytes(b"\x1b[H\x1bMX")
        assert term.grid[0][0].char == "X"

    def test_ris_restores_cursor_visibility(self, qtbot):
        term = TerminalEmulator(rows=5, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[?25l\x1bc")

        assert term._cursor_visible is True


class TestTerminalEmulatorSearch:
    def test_search_highlight(self, qtbot):
        term = TerminalEmulator(rows=3, cols=20)
        qtbot.addWidget(term)

        term.process_bytes(b"hello world")
        term.search_highlight = (0, 6, 5)
        term._render_full()

        assert term.search_highlight == (0, 6, 5)
        cursor = QTextCursor(term.document())
        cursor.setPosition(6)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 5)
        assert cursor.charFormat().background().color() == QColor(255, 200, 0)


class TestTerminalEmulatorEdgeCases:
    def test_bell_ignored(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"\x07")
        assert term.grid[0][0].char == " "

    def test_erase_display_mode_0(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"ABCDE")
        term.cursor_col = 2
        term._erase_display(0)
        assert term.grid[0][0].char == "A"
        assert term.grid[0][2].char == " "

    def test_erase_display_mode_1(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"ABCDE")
        term.cursor_col = 2
        term._erase_display(1)
        assert term.grid[0][2].char == " "
        assert term.grid[1][0].char == " "

    def test_erase_display_mode_2(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"ABCDE")
        term._erase_display(2)
        assert term.grid[0][0].char == " "
        assert term.grid[1][4].char == " "

    def test_erase_line_mode_0(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"ABCDE")
        term.cursor_col = 2
        term._erase_line(0)
        assert term.grid[0][1].char == "B"
        assert term.grid[0][2].char == " "

    def test_erase_line_mode_1(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"ABCDE")
        term.cursor_col = 2
        term._erase_line(1)
        assert term.grid[0][0].char == " "
        assert term.grid[0][2].char == " "

    def test_erase_line_mode_2(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"ABCDE")
        term._erase_line(2)
        assert term.grid[0][0].char == " "
        assert term.grid[0][4].char == " "

    def test_move_cursor_bounds(self, qtbot):
        term = TerminalEmulator(rows=3, cols=5)
        qtbot.addWidget(term)
        term._move_cursor(-100, -100)
        assert term.cursor_row == 0
        assert term.cursor_col == 0
        term._move_cursor(100, 100)
        assert term.cursor_row == 2
        assert term.cursor_col == 4

    def test_backspace_at_start(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.cursor_col = 0
        term.process_bytes(b"\x08")
        assert term.cursor_col == 0

    def test_csi_carriage_return(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"AB\x1b[1;2H")
        assert term.cursor_row == 0
        assert term.cursor_col == 1

    def test_csi_dectcem_ignored(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        # DECTCEM 光标显示/隐藏 — 忽略
        term.process_bytes(b"\x1b[?25hA\x1b[?25lB")
        assert term._esc_buf == ""
        assert term.grid[0][0].char == "A"
        assert term.grid[0][1].char == "B"

    def test_csi_unknown_ignored(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        # 不识别的 CSI 序列（含数字 + 字母 final）应被忽略
        term.process_bytes(b"\x1b[99X")
        assert term.grid[0][0].char == " "

    def test_grid_state(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"Hi")
        # 直接检查 grid 内容
        assert term.grid[0][0].char == "H"
        assert term.grid[0][1].char == "i"

    def test_set_dimensions(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.set_dimensions(4, 10)
        assert term.rows == 4
        assert term.cols == 10

    def test_clear_screen(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"ABC")
        term.clear_screen()
        assert term.grid[0][0].char == " "
        assert term.cursor_row == 0
        assert term.cursor_col == 0

    def test_process_bytes_empty(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"")  # 不抛异常

    def test_process_bytes_with_pending_esc(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term._esc_buf = "\x1b["
        term.process_bytes(b"31mRed")
        assert term.grid[0][0].char == "R"

    def test_control_chars_ignored(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        # 其他控制字符（< 0x20）应被忽略
        term.process_bytes(b"\x01\x02\x03")
        assert term.grid[0][0].char == " "

    def test_put_char_wraps_at_end(self, qtbot):
        term = TerminalEmulator(rows=2, cols=3)
        qtbot.addWidget(term)
        term.process_bytes(b"ABCDE")
        # ABC 在第 0 行，DE 在第 1 行（自动换行）
        assert term.grid[0][0].char == "A"
        assert term.grid[1][0].char == "D"

    def test_erase_display_mode_3(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"ABCDE")
        term._erase_display(3)
        assert term.grid[0][0].char == " "

    def test_render_scheduled(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        # process_bytes 后 _dirty 应为 True，触发 _schedule_render
        term.process_bytes(b"abc")
        # 等待一帧让 _do_scheduled_render 执行
        term._do_scheduled_render()
        assert term._dirty is False

    def test_newline_scrolls_when_at_bottom(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"line1\r\nline2\r\nline3\r\n")
        # 滚屏后 line3 应在可见区域内
        all_text = "".join(c.char for row in term.grid for c in row)
        assert "line3" in all_text
        assert "line1" not in all_text  # line1 被滚出

    def test_csi_dectcem_with_esc_buffer(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        # 通过不完整 CSI 测试 ESC 缓冲
        term.process_bytes(b"\x1b[")
        assert term._esc_buf == "\x1b["
        term.process_bytes(b"?25hOK")
        assert term._esc_buf == ""
        assert term.grid[0][0].char == "O"
        assert term.grid[0][1].char == "K"


class TestDecGraphicsCharset:
    def test_graphics_mode_maps_box_drawing(self, qtbot):
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b(0lqk")

        assert term.grid[0][0].char == "┌"
        assert term.grid[0][1].char == "─"
        assert term.grid[0][2].char == "┐"

    def test_graphics_vertical_bar(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b(0x")

        assert term.grid[0][0].char == "│"

    def test_esc_paren_b_returns_to_ascii(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b(0q\x1b(Bq")

        assert term.grid[0][0].char == "─"
        assert term.grid[0][1].char == "q"

    def test_other_designators_consumed_without_graphics(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b(Aq")

        assert term.grid[0][0].char == "q"

    def test_ris_resets_charset(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b(0\x1bcq")

        assert term.grid[0][0].char == "q"


class TestScrollRegion:
    def test_set_region_moves_cursor_home(self, qtbot):
        term = TerminalEmulator(rows=5, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"AB")

        term.process_bytes(b"\x1b[2;4r")

        assert term._scroll_top == 1
        assert term._scroll_bottom == 3
        assert term.cursor_row == 0
        assert term.cursor_col == 0

    def test_newline_scrolls_only_within_region(self, qtbot):
        term = TerminalEmulator(rows=5, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"top\r\nr1\r\nr2\r\nr3\r\nbot")
        term.process_bytes(b"\x1b[2;4r")
        term.process_bytes(b"\x1b[4;1H\r\n")

        # 区域外首行/末行不变，区域内上滚
        assert term.grid[0][0].char == "t"
        assert term.grid[4][0].char == "b"
        assert term.grid[1][0].char == "r"
        assert term.grid[1][1].char == "2"
        assert term.grid[3][0].char == " "
        assert term.cursor_row == 3

    def test_newline_inside_region_moves_down(self, qtbot):
        term = TerminalEmulator(rows=5, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[2;4r\x1b[2;1H\r\n")

        assert term.cursor_row == 2

    def test_bare_r_resets_to_full_screen(self, qtbot):
        term = TerminalEmulator(rows=5, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[2;4r\x1b[r")

        assert term._scroll_top == 0
        assert term._scroll_bottom == 4

    def test_invalid_region_ignored(self, qtbot):
        term = TerminalEmulator(rows=5, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[4;2r")

        assert term._scroll_top == 0
        assert term._scroll_bottom == 4

    def test_reverse_index_at_region_top_scrolls_region_down(self, qtbot):
        term = TerminalEmulator(rows=5, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"top\r\nr1\r\nr2\r\nr3\r\nbot")
        term.process_bytes(b"\x1b[2;4r\x1b[2;1H\x1bM")

        assert term.grid[0][0].char == "t"
        assert term.grid[4][0].char == "b"
        assert term.grid[1][0].char == " "
        assert term.grid[2][0].char == "r"
        assert term.grid[2][1].char == "1"

    def test_reset_clears_region(self, qtbot):
        term = TerminalEmulator(rows=5, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[2;4r\x1bc")

        assert term._scroll_top == 0
        assert term._scroll_bottom == 4


class TestEscSequences:
    def test_esc_c_full_reset(self, qtbot):
        term = TerminalEmulator(rows=3, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[31mAB")

        term.process_bytes(b"\x1bc")

        assert term.cursor_row == 0
        assert term.cursor_col == 0
        assert term.grid[0][0].char == " "
        assert term._ansi_parser.current_format.hasProperty(
            0x0BC1  # QTextFormat.Property.ForegroundBrush
        ) is False

    def test_esc_7_8_save_restore_cursor(self, qtbot):
        term = TerminalEmulator(rows=5, cols=10)
        qtbot.addWidget(term)
        term.process_bytes(b"ABCD\x1b7XY")

        assert term.cursor_col == 6

        term.process_bytes(b"\x1b8Z")

        assert term.cursor_col == 5
        assert term.grid[0][4].char == "Z"

    def test_esc_m_reverse_index_moves_up(self, qtbot):
        term = TerminalEmulator(rows=5, cols=10)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[3;1H")

        term.process_bytes(b"\x1bM")

        assert term.cursor_row == 1

    def test_esc_m_at_top_scrolls_down(self, qtbot):
        term = TerminalEmulator(rows=3, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"A\r\nB")

        term.process_bytes(b"\x1b[1;1H\x1bM")

        assert term.grid[0][0].char == " "
        assert term.grid[1][0].char == "A"
        assert term.grid[2][0].char == "B"

    def test_unknown_two_char_esc_still_skipped(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)

        # ESC+Z 消费两字符，其余字节继续正常处理
        term.process_bytes(b"\x1bZZ")

        assert term.grid[0][0].char == "Z"
        assert term.cursor_col == 1


class TestEscapeBufferLimit:
    def test_unterminated_osc_buffer_is_capped(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b]0;" + b"x" * 10000)

        assert len(term._esc_buf) <= 4096

    def test_normal_text_still_processed_after_cap(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b]0;" + b"x" * 10000)
        term._esc_buf = ""
        term.process_bytes(b"OK")

        assert term.grid[0][0].char == "O"
        assert term.grid[0][1].char == "K"


class TestMiscCoverage:
    def test_csi_f_positions_cursor(self, qtbot):
        term = TerminalEmulator(rows=5, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1b[2;3f")

        assert term.cursor_row == 1
        assert term.cursor_col == 2

    def test_ctrl_non_letter_sends_nothing(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        sent: list[bytes] = []
        term.key_pressed.connect(sent.append)

        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_1,
            Qt.KeyboardModifier.ControlModifier,
        )
        term.keyPressEvent(event)

        assert sent == []


class TestSgrFormatting:
    def test_sgr_foreground_color_written_to_cell(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[31mA")

        fmt = term.grid[0][0].fmt
        assert fmt.foreground().color() == QColor(205, 49, 49)

    def test_sgr_background_and_bold_written_to_cell(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[1;44mA")

        fmt = term.grid[0][0].fmt
        assert fmt.background().color() == QColor(36, 114, 200)
        assert fmt.fontWeight() == 700

    def test_sgr_reset_restores_default_format(self, qtbot):
        from PyQt6.QtGui import QTextFormat

        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[31mA\x1b[0mB")

        fmt = term.grid[0][1].fmt
        assert not fmt.hasProperty(QTextFormat.Property.ForegroundBrush)

    def test_sgr_bare_m_resets(self, qtbot):
        from PyQt6.QtGui import QTextFormat

        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[32mA\x1b[mB")

        fmt = term.grid[0][1].fmt
        assert not fmt.hasProperty(QTextFormat.Property.ForegroundBrush)

    def test_sgr_ignored_when_colors_disabled(self, qtbot):
        from PyQt6.QtGui import QTextFormat

        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.enable_ansi_colors = False
        term.process_bytes(b"\x1b[31mA")

        fmt = term.grid[0][0].fmt
        assert not fmt.hasProperty(QTextFormat.Property.ForegroundBrush)
        assert term.grid[0][0].char == "A"


class TestNavigationKeyMapping:
    @pytest.mark.parametrize(
        "key,expected",
        [
            (Qt.Key.Key_Insert, b"\033[2~"),
            (Qt.Key.Key_PageUp, b"\033[5~"),
            (Qt.Key.Key_PageDown, b"\033[6~"),
            (Qt.Key.Key_Delete, b"\033[3~"),
            (Qt.Key.Key_Home, b"\033[H"),
            (Qt.Key.Key_End, b"\033[F"),
        ],
    )
    def test_navigation_keys(self, qtbot, key, expected):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        sent: list[bytes] = []
        term.key_pressed.connect(sent.append)

        event = QKeyEvent(
            QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier
        )
        term.keyPressEvent(event)

        assert sent == [expected]


class TestCursorVisibility:
    def test_dectcem_hide_and_show(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        assert term._cursor_visible is True

        term.process_bytes(b"\x1b[?25l")
        assert term._cursor_visible is False

        term.process_bytes(b"\x1b[?25h")
        assert term._cursor_visible is True

    def test_other_private_modes_ignored(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[?7l\x1b[?1000h")
        assert term._cursor_visible is True

    def test_hidden_cursor_not_highlighted_in_render(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"A\x1b[?25l")
        term._cursor_phase = True
        term._render_full()

        pos = term.cursor_row * (term.cols + 1) + term.cursor_col
        cursor = term.textCursor()
        cursor.setPosition(pos)
        fmt = cursor.charFormat()
        assert fmt.background().color() != QColor(128, 128, 128)

    def test_blink_toggles_phase_and_marks_dirty(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term._cursor_phase = True
        term._dirty = False

        term._blink_cursor()

        assert term._cursor_phase is False
        assert term._dirty is True

    def test_blink_skips_render_when_cursor_hidden(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term._cursor_visible = False
        term._dirty = False

        term._blink_cursor()

        assert term._dirty is False

    def test_blink_skips_render_with_selection(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"AB")
        term._render_full()
        term.selectAll()
        term._dirty = False

        term._blink_cursor()

        assert term._dirty is False

    def test_blink_timer_follows_widget_visibility(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        assert not term._blink_timer.isActive()

        term.show()
        assert term._blink_timer.isActive()

        term.hide()
        assert not term._blink_timer.isActive()


class TestTerminalResize:
    def test_resize_grid_grow_preserves_content(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"AB")

        term.resize_grid(4, 10)

        assert term.rows == 4
        assert term.cols == 10
        # 底部锚定：内容下移，光标跟随
        assert term.grid[2][0].char == "A"
        assert term.grid[2][1].char == "B"
        assert term.cursor_row == 2
        assert term.cursor_col == 2

    def test_resize_grid_shrink_rows_drops_top(self, qtbot):
        term = TerminalEmulator(rows=3, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"one\r\ntwo\r\nth")

        term.resize_grid(2, 5)

        assert term.rows == 2
        assert term.grid[0][0].char == "t"
        assert term.grid[1][0].char == "t"
        assert term.grid[1][1].char == "h"
        assert term.cursor_row == 1
        assert term.cursor_col == 2

    def test_resize_grid_shrink_cols_truncates_and_clamps(self, qtbot):
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)
        term.process_bytes(b"ABCDEFGHIJ")

        term.resize_grid(2, 5)

        assert term.cols == 5
        assert term.grid[0][0].char == "A"
        assert term.grid[0][4].char == "E"
        assert term.cursor_col == 4
        assert term._wrap_pending is False

    def test_resize_grid_same_size_is_noop(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.process_bytes(b"AB")
        grid_before = term.grid

        term.resize_grid(2, 5)

        assert term.grid is grid_before

    def test_fit_dimensions_floors_to_cell_size(self, qtbot):
        from PyQt6.QtGui import QFontMetricsF

        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        fm = QFontMetricsF(term.font())
        cell_w = fm.horizontalAdvance("M")
        cell_h = fm.lineSpacing()

        rows, cols = term._fit_dimensions(int(cell_w * 10.7), int(cell_h * 5.2))
        assert (rows, cols) == (5, 10)

        # 过小尺寸钳制为 1x1
        assert term._fit_dimensions(1, 1) == (1, 1)

    def test_hidden_widget_does_not_resize_grid(self, qtbot):
        term = TerminalEmulator(rows=20, cols=40)
        qtbot.addWidget(term)
        term.show()
        qtbot.waitUntil(lambda: term.viewport().width() > 0)
        term.process_bytes(b"hi")
        rows_when_visible = term.rows
        row_of_content = term.cursor_row
        term.hide()

        term.resize(80, 40)
        term.resize_to_fit()

        assert term.rows == rows_when_visible
        assert "".join(c.char for c in term.grid[row_of_content]).strip() == "hi"

    def test_resize_event_updates_dimensions(self, qtbot):
        term = TerminalEmulator(rows=2, cols=5)
        qtbot.addWidget(term)
        term.show()
        term.resize(640, 480)
        qtbot.waitUntil(lambda: term.viewport().width() > 0)

        term.resize_to_fit()

        margin = term.document().documentMargin()
        expected_rows, expected_cols = term._fit_dimensions(
            int(term.viewport().width() - 2 * margin),
            int(term.viewport().height() - 2 * margin),
        )
        assert (term.rows, term.cols) == (expected_rows, expected_cols)
        assert term.rows > 2
        assert term.cols > 5
