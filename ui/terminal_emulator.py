"""
终端模拟器组件

支持 VT100/xterm 风格的终端行为：
  - 回车覆盖（\r）
  - 光标移动（\033[nA/B/C/D/H）
  - 清行/清屏（\033[K, \033[2J）
  - 光标保存/恢复（\033[s/\033[u）
  - ANSI 颜色（复用 AnsiParser）
  - 键盘输入转发到串口

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QKeyEvent,
    QTextCharFormat,
    QTextCursor,
    QColor,
    QFont,
)
from PyQt6.QtWidgets import QApplication, QTextEdit

from core.ansi_parser import AnsiParser


@dataclass
class _Cell:
    """终端网格中的一个单元格。"""

    char: str = " "
    fmt: QTextCharFormat = field(default_factory=QTextCharFormat)


_DEC_GRAPHICS = {
    "`": "◆",
    "a": "▒",
    "f": "°",
    "g": "±",
    "j": "┘",
    "k": "┐",
    "l": "┌",
    "m": "└",
    "n": "┼",
    "o": "⎺",
    "p": "⎻",
    "q": "─",
    "r": "⎼",
    "s": "⎽",
    "t": "├",
    "u": "┤",
    "v": "┴",
    "w": "┬",
    "x": "│",
    "y": "≤",
    "z": "≥",
    "{": "π",
    "|": "≠",
    "}": "£",
    "~": "·",
}


class TerminalEmulator(QTextEdit):
    """VT100 风格终端模拟器。

    维护一个字符网格，解析设备输出中的 ANSI 转义序列和光标控制码，
    将结果渲染到 QTextEdit 上。键盘事件通过 `key_pressed` 信号
    转发给当前连接的发送方。
    """

    key_pressed = pyqtSignal(bytes)
    paste_warning = pyqtSignal(int)

    _SCROLL_MARGIN: int = 5
    _ESC_BUF_LIMIT: int = 4096
    _PASTE_CONFIRM_SIZE: int = 1024
    _PASTE_CONFIRM_SECONDS: float = 3.0

    def __init__(
        self,
        rows: int = 24,
        cols: int = 80,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.rows = rows
        self.cols = cols
        self.enable_ansi_colors: bool = True
        self.font_family: str = "Consolas"
        self.search_highlight: tuple[int, int, int] | None = None

        self.setReadOnly(True)
        self.setTabChangesFocus(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._apply_font()

        # 网格：grid[row][col]
        self.grid: list[list[_Cell]] = [
            [_Cell() for _ in range(cols)] for _ in range(rows)
        ]
        self.cursor_row: int = 0
        self.cursor_col: int = 0
        self._wrap_pending: bool = False
        self._scroll_top: int = 0
        self._scroll_bottom: int = rows - 1
        self._dec_graphics: bool = False

        # 光标保存/恢复
        self._saved_row: int = 0
        self._saved_col: int = 0

        # ANSI 解析器（复用颜色格式跟踪）
        self._ansi_parser = AnsiParser()

        # 部分转义序列缓冲
        self._esc_buf: str = ""
        self._utf8_decoder = codecs.getincrementaldecoder("utf-8")(
            errors="backslashreplace"
        )

        # 多行/超大粘贴的二次确认
        self._pending_paste: tuple[str, float] | None = None
        import time

        self._paste_clock = time.monotonic

        # 渲染节流标记
        self._dirty: bool = True
        self._render_pending: bool = False

        # 光标可见性（DECTCEM）与闪烁
        self._cursor_visible: bool = True
        self._cursor_phase: bool = True
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(530)
        self._blink_timer.timeout.connect(self._blink_cursor)

        # ECMA-48: parameter bytes, intermediate bytes, final byte.
        self._csi_terminator = re.compile(r"^([0-?]*)([ -/]*)([@-~])")

    # ── 公共 API ─────────────────────────────────────────────

    def process_bytes(self, data: bytes) -> None:
        """处理来自串口的原始字节。"""
        if not data:
            return

        decoded = self._utf8_decoder.decode(data, final=False)
        if self._esc_buf:
            text = self._esc_buf + decoded
            self._esc_buf = ""
        else:
            text = decoded

        self._process_text(text)

        if self._dirty:
            self._schedule_render()

    def clear_screen(self) -> None:
        """清空整个终端。"""
        self.grid = [[_Cell() for _ in range(self.cols)] for _ in range(self.rows)]
        self.cursor_row = 0
        self.cursor_col = 0
        self._wrap_pending = False
        self._dirty = True
        self._render_full()

    def set_dimensions(self, rows: int, cols: int) -> None:
        """调整终端行列数。"""
        self.rows = rows
        self.cols = cols
        self._saved_row = max(0, min(self._saved_row, rows - 1))
        self._saved_col = max(0, min(self._saved_col, cols - 1))
        self._scroll_top = 0
        self._scroll_bottom = rows - 1
        self.clear_screen()

    def resize_grid(self, rows: int, cols: int) -> None:
        """调整网格尺寸并保留内容（底部锚定，光标钳制）。"""
        rows = max(1, int(rows))
        cols = max(1, int(cols))
        if rows == self.rows and cols == self.cols:
            return

        if cols != self.cols:
            for row in self.grid:
                if cols > self.cols:
                    row.extend(_Cell() for _ in range(cols - self.cols))
                else:
                    del row[cols:]

        if rows > self.rows:
            blank = [[_Cell() for _ in range(cols)] for _ in range(rows - self.rows)]
            self.grid = blank + self.grid
            self.cursor_row += rows - self.rows
        elif rows < self.rows:
            drop = self.rows - rows
            # 优先丢弃光标下方的空白行，避免缩小窗口时抹掉已有输出
            spare = 0
            for index in range(len(self.grid) - 1, self.cursor_row, -1):
                if any(cell.char != " " for cell in self.grid[index]):
                    break
                spare += 1
            drop_bottom = min(drop, spare)
            if drop_bottom:
                del self.grid[len(self.grid) - drop_bottom :]
            drop_top = drop - drop_bottom
            if drop_top:
                self.grid = self.grid[drop_top:]
                self.cursor_row -= drop_top

        self.rows = rows
        self.cols = cols
        self.cursor_row = max(0, min(self.cursor_row, rows - 1))
        self.cursor_col = max(0, min(self.cursor_col, cols - 1))
        self._saved_row = max(0, min(self._saved_row, rows - 1))
        self._saved_col = max(0, min(self._saved_col, cols - 1))
        self._wrap_pending = False
        self._scroll_top = 0
        self._scroll_bottom = rows - 1
        self._dirty = True
        self._schedule_render()

    def _fit_dimensions(self, width: int, height: int) -> tuple[int, int]:
        """按可用像素和字体度量计算可容纳的行列数。"""
        from PyQt6.QtGui import QFontMetricsF

        fm = QFontMetricsF(self.font())
        cell_w = max(1.0, fm.horizontalAdvance("M"))
        cell_h = max(1.0, fm.lineSpacing())
        cols = max(1, int(width // cell_w))
        rows = max(1, int(height // cell_h))
        return rows, cols

    def resize_to_fit(self) -> None:
        """按当前视口尺寸调整网格；隐藏时不调整，避免布局回收尺寸导致内容丢失。"""
        if not self.isVisible():
            return
        margin = self.document().documentMargin()
        width = max(0, int(self.viewport().width() - 2 * margin))
        height = max(0, int(self.viewport().height() - 2 * margin))
        rows, cols = self._fit_dimensions(width, height)
        if (rows, cols) != (self.rows, self.cols):
            self.resize_grid(rows, cols)

    def focusNextPrevChild(self, next: bool) -> bool:  # noqa: A002
        """终端独占 Tab：只读 QTextEdit 默认会用 Tab 切换焦点，这里禁止。"""
        return False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resize_to_fit()

    # ── 键盘事件 ─────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        mod = event.modifiers()

        if (
            mod & Qt.KeyboardModifier.ControlModifier
            and mod & Qt.KeyboardModifier.ShiftModifier
        ):
            if key == Qt.Key.Key_C:
                self.copy()
                return
            if key == Qt.Key.Key_V:
                self._paste_clipboard()
                return

        # Ctrl+字母 → 控制字符
        if (
            mod & Qt.KeyboardModifier.ControlModifier
            and Qt.Key.Key_A <= key <= Qt.Key.Key_Z
        ):
            self.key_pressed.emit(bytes([key - Qt.Key.Key_A + 1]))
            return

        # 特殊键映射
        special = {
            Qt.Key.Key_Return: b"\r",
            Qt.Key.Key_Enter: b"\r",
            Qt.Key.Key_Backspace: b"\x7f",
            Qt.Key.Key_Insert: b"\033[2~",
            Qt.Key.Key_Delete: b"\033[3~",
            Qt.Key.Key_PageUp: b"\033[5~",
            Qt.Key.Key_PageDown: b"\033[6~",
            Qt.Key.Key_Tab: b"\t",
            Qt.Key.Key_Escape: b"\x1b",
            Qt.Key.Key_Up: b"\033[A",
            Qt.Key.Key_Down: b"\033[B",
            Qt.Key.Key_Right: b"\033[C",
            Qt.Key.Key_Left: b"\033[D",
            Qt.Key.Key_Home: b"\033[H",
            Qt.Key.Key_End: b"\033[F",
            Qt.Key.Key_F1: b"\033OP",
            Qt.Key.Key_F2: b"\033OQ",
            Qt.Key.Key_F3: b"\033OR",
            Qt.Key.Key_F4: b"\033OS",
            Qt.Key.Key_F5: b"\033[15~",
            Qt.Key.Key_F6: b"\033[17~",
            Qt.Key.Key_F7: b"\033[18~",
            Qt.Key.Key_F8: b"\033[19~",
            Qt.Key.Key_F9: b"\033[20~",
            Qt.Key.Key_F10: b"\033[21~",
            Qt.Key.Key_F11: b"\033[23~",
            Qt.Key.Key_F12: b"\033[24~",
        }

        if key in special:
            self.key_pressed.emit(special[key])
            return

        # 普通文本
        text = event.text()
        if text and text.isprintable():
            self.key_pressed.emit(text.encode("utf-8"))

    def _paste_clipboard(self) -> None:
        """粘贴剪贴板；多行或超大内容需 3 秒内二次确认。"""
        text = QApplication.clipboard().text()
        if not text:
            return

        risky = (
            "\n" in text or "\r" in text or len(text) > self._PASTE_CONFIRM_SIZE
        )
        if not risky:
            self.key_pressed.emit(text.encode("utf-8"))
            return

        now = self._paste_clock()
        if (
            self._pending_paste is not None
            and self._pending_paste[0] == text
            and now - self._pending_paste[1] < self._PASTE_CONFIRM_SECONDS
        ):
            self._pending_paste = None
            self.key_pressed.emit(text.encode("utf-8"))
            return

        self._pending_paste = (text, now)
        self.paste_warning.emit(text.count("\n") + 1)

    def _buffer_escape(self, text: str) -> None:
        """缓冲不完整转义序列；超限则丢弃，避免无界增长。"""
        self._esc_buf = "" if len(text) > self._ESC_BUF_LIMIT else text

    # ── 内部：文本处理 ───────────────────────────────────────

    def _process_text(self, text: str) -> None:
        """逐字符处理文本，更新网格状态。"""
        i = 0
        length = len(text)

        while i < length:
            ch = text[i]

            # ── 转义序列 ──
            if ch == "\x1b":
                if i + 1 < length and text[i + 1] == "[":
                    rest = text[i + 2 :]
                    m = self._csi_terminator.match(rest)
                    if m:
                        params_str = m.group(1)
                        final_char = m.group(3)
                        consumed = i + 2 + m.end()
                        self._handle_csi(params_str, final_char)
                        i = consumed
                        continue
                    else:
                        # CSI 不完整，缓冲等待更多数据
                        self._buffer_escape(text[i:])
                        return
                elif i + 1 < length and text[i + 1] in "]PX^_":
                    allow_bel = text[i + 1] == "]"
                    end = self._find_control_string_end(text, i + 2, allow_bel)
                    if end is None:
                        self._buffer_escape(text[i:])
                        return
                    i = end
                    continue
                elif i + 1 < length and text[i + 1] == "(":
                    # 字符集切换：ESC ( 0 = DEC 图形，其他 = ASCII
                    if i + 2 < length:
                        self._dec_graphics = text[i + 2] == "0"
                        i += 3
                    else:
                        self._esc_buf = text[i:]
                        return
                    continue
                elif i + 1 < length:
                    nxt = text[i + 1]
                    if nxt == "c":
                        self._reset()
                    elif nxt == "7":
                        self._saved_row = self.cursor_row
                        self._saved_col = self.cursor_col
                    elif nxt == "8":
                        self.cursor_row = self._saved_row
                        self.cursor_col = self._saved_col
                        self._wrap_pending = False
                        self._dirty = True
                    elif nxt == "M":
                        self._reverse_index()
                    # 其他两字符 ESC 序列忽略
                    i += 2
                    continue
                else:
                    # ESC 在末尾
                    self._esc_buf = "\x1b"
                    return

            # ── 回车 ──
            elif ch == "\r":
                self.cursor_col = 0
                self._wrap_pending = False
                i += 1
                self._dirty = True

            # ── 换行 ──
            elif ch == "\n":
                self._wrap_pending = False
                self._newline()
                i += 1
                self._dirty = True

            # ── 制表符 ──
            elif ch == "\t":
                next_stop = ((self.cursor_col // 8) + 1) * 8
                stop = min(next_stop, self.cols - 1)
                while self.cursor_col < stop:
                    self._put_char(" ")
                i += 1
                self._dirty = True

            # ── 响铃 ──
            elif ch == "\x07":
                i += 1

            # ── 退格 ──
            elif ch == "\x08":
                self._wrap_pending = False
                if self.cursor_col > 0:
                    self.cursor_col -= 1
                i += 1
                self._dirty = True

            # ── 普通字符 ──
            elif ch >= " ":
                if self._dec_graphics:
                    ch = _DEC_GRAPHICS.get(ch, ch)
                self._put_char(ch)
                i += 1
                self._dirty = True

            # ── 其他控制字符 ──
            else:
                i += 1

    @staticmethod
    def _find_control_string_end(
        text: str, start: int, allow_bel: bool
    ) -> int | None:
        endings: list[tuple[int, int]] = []
        st_index = text.find("\x1b\\", start)
        if st_index >= 0:
            endings.append((st_index, 2))
        if allow_bel:
            bel_index = text.find("\x07", start)
            if bel_index >= 0:
                endings.append((bel_index, 1))
        if not endings:
            return None
        index, size = min(endings)
        return index + size

    def _put_char(self, ch: str) -> None:
        """在光标位置写入字符并前进光标。"""
        if self._wrap_pending:
            self.cursor_col = 0
            self._newline()
            self._wrap_pending = False

        cell = self.grid[self.cursor_row][self.cursor_col]
        cell.char = ch
        cell.fmt = QTextCharFormat(self._ansi_parser.current_format)
        if self.cursor_col == self.cols - 1:
            self._wrap_pending = True
        else:
            self.cursor_col += 1

    def _newline(self) -> None:
        """光标下移一行，到达滚动区域底部则区域内滚屏。"""
        if self.cursor_row == self._scroll_bottom:
            blank = [_Cell() for _ in range(self.cols)]
            self.grid.pop(self._scroll_top)
            self.grid.insert(self._scroll_bottom, blank)
        elif self.cursor_row < self.rows - 1:
            self.cursor_row += 1

    def _reset(self) -> None:
        """RIS（ESC c）：完整复位终端状态。"""
        self.grid = [[_Cell() for _ in range(self.cols)] for _ in range(self.rows)]
        self.cursor_row = 0
        self.cursor_col = 0
        self._saved_row = 0
        self._saved_col = 0
        self._wrap_pending = False
        self._scroll_top = 0
        self._scroll_bottom = self.rows - 1
        self._dec_graphics = False
        self._cursor_visible = True
        self._ansi_parser.reset_format()
        self._dirty = True
        self._schedule_render()

    def _reverse_index(self) -> None:
        """RI（ESC M）：光标上移一行，到达滚动区域顶部则区域内下滚。"""
        if self.cursor_row == self._scroll_top:
            blank = [_Cell() for _ in range(self.cols)]
            self.grid.pop(self._scroll_bottom)
            self.grid.insert(self._scroll_top, blank)
        elif self.cursor_row > 0:
            self.cursor_row -= 1
        self._wrap_pending = False
        self._dirty = True

    def _handle_private_mode(self, mode: str, enable: bool) -> None:
        """处理私有模式设置（\033[?nh/l），当前支持 DECTCEM（25）。"""
        if mode == "25":
            self._cursor_visible = enable
            self._dirty = True
            self._schedule_render()

    def _blink_cursor(self) -> None:
        """切换光标闪烁相位；隐藏或有选区时跳过重绘。"""
        self._cursor_phase = not self._cursor_phase
        if self._cursor_visible and not self.textCursor().hasSelection():
            self._dirty = True
            self._schedule_render()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._blink_timer.start()

    def hideEvent(self, event) -> None:
        self._blink_timer.stop()
        super().hideEvent(event)

    # ── 内部：CSI 序列处理 ────────────────────────────────────

    def _handle_csi(self, params_str: str, final: str) -> None:
        """处理 CSI（\033[...X）序列。"""
        if params_str.startswith("?"):
            if final in ("h", "l"):
                self._handle_private_mode(params_str[1:], final == "h")
            return

        if any(ch not in "0123456789;" for ch in params_str):
            return

        params = (
            [int(p) if p else 0 for p in params_str.split(";")] if params_str else [0]
        )
        p1 = params[0] if params else 0

        if final == "m":
            # SGR — 设置图形渲染属性（颜色、粗体等）
            if self.enable_ansi_colors:
                code = params_str + "m"
                self._ansi_parser.parse_code(code)
        elif final == "K":
            self._erase_line(p1)
        elif final == "J":
            self._erase_display(p1)
        elif final == "A":
            self._move_cursor(0, -max(p1, 1))
        elif final == "B":
            self._move_cursor(0, max(p1, 1))
        elif final == "C":
            self._move_cursor(max(p1, 1), 0)
        elif final == "D":
            self._move_cursor(-max(p1, 1), 0)
        elif final == "H" or final == "f":
            row = max(params[0] if params else 1, 1) - 1
            col = max(params[1] if len(params) > 1 else 1, 1) - 1
            self.cursor_row = min(row, self.rows - 1)
            self.cursor_col = min(col, self.cols - 1)
            self._wrap_pending = False
            self._dirty = True
        elif final == "r":
            top = params[0] if params and params[0] else 1
            bottom = params[1] if len(params) > 1 and params[1] else self.rows
            if 1 <= top < bottom <= self.rows:
                self._scroll_top = top - 1
                self._scroll_bottom = bottom - 1
                self.cursor_row = 0
                self.cursor_col = 0
                self._wrap_pending = False
                self._dirty = True
        elif final == "s":
            self._saved_row = self.cursor_row
            self._saved_col = self.cursor_col
        elif final == "u":
            self.cursor_row = self._saved_row
            self.cursor_col = self._saved_col
            self._wrap_pending = False
            self._dirty = True
        elif final in ("l", "h"):
            # DECTCEM 光标显示/隐藏 — 忽略
            pass

    # ── 内部：光标移动 ───────────────────────────────────────

    def _move_cursor(self, dx: int, dy: int) -> None:
        self.cursor_row = max(0, min(self.rows - 1, self.cursor_row + dy))
        self.cursor_col = max(0, min(self.cols - 1, self.cursor_col + dx))
        self._wrap_pending = False
        self._dirty = True

    # ── 内部：擦除操作 ───────────────────────────────────────

    def _erase_display(self, mode: int) -> None:
        self._wrap_pending = False
        if mode == 0:
            # 从光标到屏幕末尾
            for c in range(self.cursor_col, self.cols):
                self.grid[self.cursor_row][c] = _Cell()
            for r in range(self.cursor_row + 1, self.rows):
                self.grid[r] = [_Cell() for _ in range(self.cols)]
        elif mode == 1:
            # 从屏幕开头到光标
            for r in range(0, self.cursor_row):
                self.grid[r] = [_Cell() for _ in range(self.cols)]
            for c in range(0, self.cursor_col + 1):
                self.grid[self.cursor_row][c] = _Cell()
        elif mode == 2 or mode == 3:
            self.grid = [[_Cell() for _ in range(self.cols)] for _ in range(self.rows)]
        self._dirty = True

    def _erase_line(self, mode: int) -> None:
        self._wrap_pending = False
        if mode == 0:
            # 从光标到行尾
            for c in range(self.cursor_col, self.cols):
                self.grid[self.cursor_row][c] = _Cell()
        elif mode == 1:
            # 从行首到光标
            for c in range(0, self.cursor_col + 1):
                self.grid[self.cursor_row][c] = _Cell()
        elif mode == 2:
            # 整行清除
            self.grid[self.cursor_row] = [_Cell() for _ in range(self.cols)]
        self._dirty = True

    # ── 内部：渲染 ───────────────────────────────────────────

    def _apply_font(self) -> None:
        font = QFont(self.font_family, 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)

    def _schedule_render(self) -> None:
        """通过事件循环节流渲染。"""
        if not self._render_pending:
            self._render_pending = True
            from PyQt6.QtCore import QTimer

            QTimer.singleShot(0, self._do_scheduled_render)

    def _do_scheduled_render(self) -> None:
        self._render_pending = False
        if self._dirty:
            self._render_full()

    def _render_full(self) -> None:
        """从网格重建整个 QTextEdit 内容（含 ANSI 颜色 + 光标高亮）。"""
        self._dirty = False

        sb = self.verticalScrollBar()
        at_bottom = sb and sb.value() >= sb.maximum() - self._SCROLL_MARGIN

        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.beginEditBlock()

        cursor_fmt = QTextCharFormat()
        cursor_fmt.setBackground(QColor(128, 128, 128))
        cursor_fmt.setForeground(QColor(255, 255, 255))

        search_fmt = QTextCharFormat()
        search_fmt.setBackground(QColor(255, 200, 0))
        search_fmt.setForeground(QColor(0, 0, 0))

        cursor_active = self._cursor_visible and self._cursor_phase

        for row_idx, row in enumerate(self.grid):
            if row_idx > 0:
                cursor.insertText("\n")

            for col_idx, cell in enumerate(row):
                if (
                    self.search_highlight is not None
                    and row_idx == self.search_highlight[0]
                    and self.search_highlight[1]
                    <= col_idx
                    < self.search_highlight[1] + self.search_highlight[2]
                ):
                    cursor.insertText(cell.char, search_fmt)
                elif (
                    cursor_active
                    and row_idx == self.cursor_row
                    and col_idx == self.cursor_col
                ):
                    cursor.insertText(cell.char, cursor_fmt)
                else:
                    cursor.insertText(cell.char, QTextCharFormat(cell.fmt))

        cursor.endEditBlock()

        if at_bottom:
            self.moveCursor(QTextCursor.MoveOperation.End)

