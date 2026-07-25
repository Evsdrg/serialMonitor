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
        qapp.clipboard().setText("你好\n")
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

        assert received == ["你好\n".encode("utf-8")]


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
