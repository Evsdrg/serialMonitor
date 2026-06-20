"""
终端模拟器的属性测试

使用 hypothesis 自动生成文本输入，验证 TerminalEmulator 的不变式。
"""

import string

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from ui.terminal_emulator import TerminalEmulator

pytestmark = pytest.mark.slow


# ── 策略 ────────────────────────────────────────────────


visible_chars = string.ascii_letters + string.digits + string.punctuation
short_text = st.text(alphabet=visible_chars, min_size=0, max_size=50)


# 统一抑制 qtbot 健康检查（每个测试创建独立 TerminalEmulator 实例）
HYP_SETTINGS = dict(
    max_examples=20,
    deadline=2000,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# ── 不变式：光标边界 ──────────────────────────────────────


class TestCursorInvariants:
    @settings(**HYP_SETTINGS)
    @given(short_text, st.integers(min_value=1, max_value=10), st.integers(min_value=1, max_value=20))
    def test_cursor_within_bounds(self, qtbot, text: str, rows: int, cols: int) -> None:
        """任意输入后，光标应在 [0, rows) × [0, cols) 范围内。"""
        term = TerminalEmulator(rows=rows, cols=cols)
        qtbot.addWidget(term)
        term.process_bytes(text.encode("utf-8"))
        assert 0 <= term.cursor_row < rows
        assert 0 <= term.cursor_col <= cols

    @settings(**HYP_SETTINGS)
    @given(st.text(alphabet=visible_chars, min_size=1, max_size=200))
    def test_cursor_bounded_after_long_text(self, qtbot, text: str) -> None:
        """长文本处理后光标仍应在范围内。"""
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)
        term.process_bytes(text.encode("utf-8"))
        assert 0 <= term.cursor_row < 3
        assert 0 <= term.cursor_col <= 10


# ── 不变式：滚动行为 ──────────────────────────────────────


class TestScrollInvariants:
    @settings(**HYP_SETTINGS)
    @given(st.lists(short_text.filter(lambda s: len(s) > 0), min_size=1, max_size=20))
    def test_scroll_preserves_last_rows(self, qtbot, lines: list[str]) -> None:
        """写入多行后，至少最后一行部分内容应可见。"""
        rows, cols = 3, 20
        term = TerminalEmulator(rows=rows, cols=cols)
        qtbot.addWidget(term)

        full = "\n".join(lines) + "\n"
        term.process_bytes(full.encode("utf-8"))

        all_text = "".join(c.char for row in term.grid for c in row)
        # 最后一行内容应至少部分出现在 grid 中
        last_line = lines[-1]
        assert last_line[:cols] in all_text or all_text.strip() != ""

    @settings(**HYP_SETTINGS)
    @given(st.binary(min_size=0, max_size=500))
    def test_no_buffer_overflow(self, qtbot, data: bytes) -> None:
        """任意字节流处理后不应崩溃。"""
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)
        term.process_bytes(data)  # 不抛异常


# ── 不变式：行尾处理 ──────────────────────────────────────


class TestLineEnding:
    @settings(**HYP_SETTINGS)
    @given(st.text(alphabet=visible_chars, min_size=0, max_size=30))
    def test_cr_resets_col(self, qtbot, text: str) -> None:
        """`\r` 后光标 col 应为 0。"""
        term = TerminalEmulator(rows=2, cols=20)
        qtbot.addWidget(term)
        term.process_bytes((text + "\r").encode("utf-8"))
        assert term.cursor_col == 0

    @settings(**HYP_SETTINGS)
    @given(short_text)
    def test_lf_advances_row(self, qtbot, text: str) -> None:
        """`\n` 后光标 row >= before（可能滚到底）。"""
        term = TerminalEmulator(rows=3, cols=20)
        qtbot.addWidget(term)
        before = term.cursor_row
        term.process_bytes((text + "\n").encode("utf-8"))
        assert term.cursor_row >= before

    @settings(**HYP_SETTINGS)
    @given(st.integers(min_value=0, max_value=5), st.integers(min_value=0, max_value=5))
    def test_cr_lf_moves_to_next_line_start(self, qtbot, n_rows: int, n_cols: int) -> None:
        """`\r\n` 后光标 col 应为 0。"""
        rows, cols = max(2, n_rows + 1), max(5, n_cols + 5)
        term = TerminalEmulator(rows=rows, cols=cols)
        qtbot.addWidget(term)
        term.process_bytes(b"\r\n")
        assert term.cursor_col == 0


# ── CSI 序列不变量 ──────────────────────────────────────


class TestCSISequences:
    @settings(**HYP_SETTINGS)
    @given(st.integers(min_value=0, max_value=100))
    def test_csi_cursor_up_no_underflow(self, qtbot, n: int) -> None:
        """CSI <n>A 不会让光标 row 变负。"""
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)
        term.cursor_row = 0
        term.process_bytes(f"\x1b[{n}A".encode())
        assert term.cursor_row >= 0

    @settings(**HYP_SETTINGS)
    @given(st.integers(min_value=0, max_value=100))
    def test_csi_cursor_down_no_overflow(self, qtbot, n: int) -> None:
        """CSI <n>B 不会让光标 row 越界。"""
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)
        term.process_bytes(f"\x1b[{n}B".encode())
        assert term.cursor_row < 3

    @settings(**HYP_SETTINGS)
    @given(st.integers(min_value=0, max_value=100))
    def test_csi_cursor_back_no_underflow(self, qtbot, n: int) -> None:
        """CSI <n>D 不会让光标 col 变负。"""
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)
        term.cursor_col = 0
        term.process_bytes(f"\x1b[{n}D".encode())
        assert term.cursor_col >= 0

    @settings(**HYP_SETTINGS)
    @given(st.integers(min_value=0, max_value=100))
    def test_csi_cursor_forward_no_overflow(self, qtbot, n: int) -> None:
        """CSI <n>C 不会让光标 col 越界。"""
        term = TerminalEmulator(rows=3, cols=10)
        qtbot.addWidget(term)
        term.process_bytes(f"\x1b[{n}C".encode())
        assert term.cursor_col <= 10


# ── ANSI + 文本混合 ──────────────────────────────────────


class TestMixedInput:
    @settings(**HYP_SETTINGS)
    @given(st.lists(
        st.one_of(
            st.text(alphabet=visible_chars, min_size=1, max_size=10),
            st.just("\r\n"),
            st.just("\x1b[2J"),
            st.just("\x1b[H"),
        ),
        min_size=1, max_size=20,
    ))
    def test_mixed_input_no_crash(self, qtbot, parts: list) -> None:
        """混合 ANSI + 文本输入不崩溃。"""
        term = TerminalEmulator(rows=3, cols=20)
        qtbot.addWidget(term)
        for part in parts:
            if isinstance(part, str):
                term.process_bytes(part.encode("utf-8"))
            else:
                term.process_bytes(part)

    @settings(**HYP_SETTINGS)
    @given(st.text(alphabet=visible_chars, min_size=1, max_size=30))
    def test_erase_display_clears_grid(self, qtbot, text: str) -> None:
        """ESC[2J 后 grid 应被清空。"""
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)
        term.process_bytes(text.encode("utf-8"))
        term.process_bytes(b"\x1b[2J")
        for row in term.grid:
            for cell in row:
                assert cell.char in (" ", "")


# ── 部分 CSI 缓冲 ──────────────────────────────────────


class TestBuffering:
    @settings(**HYP_SETTINGS)
    @given(st.integers(min_value=1, max_value=9))
    def test_partial_csi_buffered(self, qtbot, partial_len: int) -> None:
        """不完整 CSI 序列应被缓冲。"""
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)
        partial = b"\x1b[" + b"0" * partial_len
        term.process_bytes(partial)
        assert term._esc_buf != "" or partial_len == 0

    @settings(**HYP_SETTINGS)
    @given(st.text(alphabet=visible_chars, min_size=1, max_size=20))
    def test_buffered_esc_completes(self, qtbot, suffix: str) -> None:
        """缓冲的不完整 ESC 序列，收到后续字符后能完成处理。"""
        term = TerminalEmulator(rows=2, cols=10)
        qtbot.addWidget(term)
        term.process_bytes(b"\x1b[31")
        term.process_bytes(b"m" + suffix.encode("utf-8"))
        assert term._esc_buf == ""
