"""
测试 ui/terminal_emulator.py
"""

import pytest

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

from ui.terminal_emulator import TerminalEmulator, _Cell


class TestTerminalEmulatorBasic:
    def test_initial_dimensions(self, qtbot):
        term = TerminalEmulator(rows=10, cols=40)
        qtbot.addWidget(term)
        assert term.rows == 10
        assert term.cols == 40
        assert len(term.grid) == 10
        assert len(term.grid[0]) == 40

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

        term.process_bytes(b"abcd")
        assert term.grid[0][0].char == "a"
        assert term.grid[0][2].char == "c"
        assert term.grid[1][0].char == "d"

    def test_scroll_up(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"line1\nline2\nline3\nline4")
        assert term.grid[1][0].char == "l"
        assert term.grid[1][4].char == "3"
        assert term.grid[2][5].char == "l"
        assert term.grid[2][9].char == "4"


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
        assert term.grid[0][4].char == "4"
        assert term.grid[0][5].char == " "
        assert term.grid[0][0].char == "0"

    def test_csi_erase_display(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"hello\nworld\x1b[2Jx")
        assert term.grid[0][0].char == " "
        assert term.grid[2][0].char == "x"

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

    def test_non_csi_escape_ignored(self, qtbot):
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)

        term.process_bytes(b"\x1bPignored")
        assert term.grid[0][0].char == "i"


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


class TestTerminalEmulatorSearch:
    def test_search_highlight(self, qtbot):
        term = TerminalEmulator(rows=3, cols=20)
        qtbot.addWidget(term)

        term.process_bytes(b"hello world")
        term.search_highlight = (0, 6)
        assert term.search_highlight == (0, 6)


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
        term.process_bytes(b"\x1b[?25h")
        term.process_bytes(b"\x1b[?25l")
        # 不应抛异常
        assert term.cursor_row == 0

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
        term.process_bytes(b"line1\nline2\nline3\n")
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
        # 不被 regex 识别的内容会保留在缓冲
        term.process_bytes(b"?25h")
        assert term._esc_buf == "\x1b[?25h"
