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

import re
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (
    QKeyEvent,
    QTextCharFormat,
    QTextCursor,
    QColor,
    QFont,
)
from PyQt6.QtWidgets import QTextEdit

from core.ansi_parser import AnsiParser
from core.ansi import strip_ansi


@dataclass
class _Cell:
    """终端网格中的一个单元格。"""

    char: str = " "
    fmt: QTextCharFormat = field(default_factory=QTextCharFormat)


class TerminalEmulator(QTextEdit):
    """VT100 风格终端模拟器。

    维护一个字符网格，解析设备输出中的 ANSI 转义序列和光标控制码，
    将结果渲染到 QTextEdit 上。键盘事件通过 `key_pressed` 信号
    转发给串口发送方。
    """

    key_pressed = pyqtSignal(bytes)

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

        self.setReadOnly(True)
        self.setTabChangesFocus(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._apply_font()

        # 网格：grid[row][col]
        self.grid: list[list[_Cell]] = [
            [_Cell() for _ in range(cols)] for _ in range(rows)
        ]
        self.cursor_row: int = 0
        self.cursor_col: int = 0

        # 光标保存/恢复
        self._saved_row: int = 0
        self._saved_col: int = 0

        # ANSI 解析器（复用颜色格式跟踪）
        self._ansi_parser = AnsiParser()

        # 部分转义序列缓冲
        self._esc_buf: str = ""

        # 渲染节流标记
        self._dirty: bool = True
        self._render_pending: bool = False

        # ESC 序列终止符正则
        self._csi_terminator = re.compile(r"^(\d*(?:;\d*)*)([A-Za-z])")

    # ── 公共 API ─────────────────────────────────────────────

    def process_bytes(self, data: bytes) -> None:
        """处理来自串口的原始字节。"""
        if not data:
            return

        if self._esc_buf:
            text = self._esc_buf + data.decode("utf-8", errors="backslashreplace")
            self._esc_buf = ""
        else:
            text = data.decode("utf-8", errors="backslashreplace")

        self._process_text(text)

        if self._dirty:
            self._schedule_render()

    def clear_screen(self) -> None:
        """清空整个终端。"""
        self.grid = [[_Cell() for _ in range(self.cols)] for _ in range(self.rows)]
        self.cursor_row = 0
        self.cursor_col = 0
        self._dirty = True
        self._render_full()

    def set_dimensions(self, rows: int, cols: int) -> None:
        """调整终端行列数。"""
        self.rows = rows
        self.cols = cols
        self.clear_screen()

    # ── 键盘事件 ─────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        mod = event.modifiers()

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
            Qt.Key.Key_Delete: b"\033[3~",
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
                        final_char = m.group(2)
                        consumed = 2 + m.end()
                        self._handle_csi(params_str, final_char)
                        i = consumed
                        continue
                    else:
                        # CSI 不完整，缓冲等待更多数据
                        self._esc_buf = text[i:]
                        return
                elif i + 1 < length:
                    # 非 CSI 的 ESC 序列，跳过两个字符
                    i += 2
                    continue
                else:
                    # ESC 在末尾
                    self._esc_buf = "\x1b"
                    return

            # ── 回车 ──
            elif ch == "\r":
                self.cursor_col = 0
                i += 1
                self._dirty = True

            # ── 换行 ──
            elif ch == "\n":
                self._newline()
                i += 1
                self._dirty = True

            # ── 制表符 ──
            elif ch == "\t":
                next_stop = ((self.cursor_col // 8) + 1) * 8
                while self.cursor_col < min(next_stop, self.cols):
                    self._put_char(" ")
                i += 1
                self._dirty = True

            # ── 响铃 ──
            elif ch == "\x07":
                i += 1

            # ── 退格 ──
            elif ch == "\x08":
                if self.cursor_col > 0:
                    self.cursor_col -= 1
                i += 1
                self._dirty = True

            # ── 普通字符 ──
            elif ch >= " ":
                self._put_char(ch)
                i += 1
                self._dirty = True

            # ── 其他控制字符 ──
            else:
                i += 1

    def _put_char(self, ch: str) -> None:
        """在光标位置写入字符并前进光标。"""
        if self.cursor_col >= self.cols:
            self.cursor_col = 0
            self._newline()

        cell = self.grid[self.cursor_row][self.cursor_col]
        cell.char = ch
        cell.fmt = QTextCharFormat(self._ansi_parser.current_format)
        self.cursor_col += 1

    def _newline(self) -> None:
        """光标下移一行，必要时滚屏。"""
        self.cursor_row += 1
        if self.cursor_row >= self.rows:
            self.grid.pop(0)
            self.grid.append([_Cell() for _ in range(self.cols)])
            self.cursor_row = self.rows - 1

    def _scroll_up(self) -> None:
        """滚屏一行（内容上移）。"""
        self.grid.pop(0)
        self.grid.append([_Cell() for _ in range(self.cols)])

    # ── 内部：CSI 序列处理 ────────────────────────────────────

    def _handle_csi(self, params_str: str, final: str) -> None:
        """处理 CSI（\033[...X）序列。"""
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
            self._dirty = True
        elif final == "s":
            self._saved_row = self.cursor_row
            self._saved_col = self.cursor_col
        elif final == "u":
            self.cursor_row = self._saved_row
            self.cursor_col = self._saved_col
            self._dirty = True
        elif final in ("l", "h"):
            # DECTCEM 光标显示/隐藏 — 忽略
            pass

    # ── 内部：光标移动 ───────────────────────────────────────

    def _move_cursor(self, dx: int, dy: int) -> None:
        self.cursor_row = max(0, min(self.rows - 1, self.cursor_row + dy))
        self.cursor_col = max(0, min(self.cols - 1, self.cursor_col + dx))
        self._dirty = True

    # ── 内部：擦除操作 ───────────────────────────────────────

    def _erase_display(self, mode: int) -> None:
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
            # 整屏清除
            self.grid = [[_Cell() for _ in range(self.cols)] for _ in range(self.rows)]
            self.cursor_row = 0
            self.cursor_col = 0
        self._dirty = True

    def _erase_line(self, mode: int) -> None:
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
        at_bottom = sb and sb.value() >= sb.maximum() - 5

        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.MoveOperation.Document)
        cursor.beginEditBlock()

        # 光标位置的高亮格式
        cursor_fmt = QTextCharFormat()
        cursor_fmt.setBackground(QColor(128, 128, 128))
        cursor_fmt.setForeground(QColor(255, 255, 255))

        for row_idx, row in enumerate(self.grid):
            if row_idx > 0:
                cursor.insertText("\n")

            for col_idx, cell in enumerate(row):
                if row_idx == self.cursor_row and col_idx == self.cursor_col:
                    cursor.insertText(cell.char, cursor_fmt)
                else:
                    cursor.insertText(cell.char, QTextCharFormat(cell.fmt))

        cursor.endEditBlock()

        if at_bottom:
            self.moveCursor(QTextCursor.MoveOperation.End)

    def _render_cursor_block(self, row: int, col: int) -> None:
        """仅更新光标位置的高亮（用于光标闪烁，暂未启用）。"""
        pass
