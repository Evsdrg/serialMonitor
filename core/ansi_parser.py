"""
ANSI 转义序列解析器

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

import re
from typing import Any

from PyQt6.QtGui import QColor, QFont, QTextCharFormat


class AnsiParser:
    """ANSI 转义序列解析器，支持彩色日志显示"""

    def __init__(self) -> None:
        self.enabled: bool = True
        self.setup()

    def setup(self) -> None:
        """初始化解析器"""
        self.ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        self.ansi_color_pattern = re.compile(r"\x1B\[([0-9;]*)m")

        self.fg_colors: dict[str, QColor] = {
            "30": QColor(0, 0, 0),
            "31": QColor(205, 49, 49),
            "32": QColor(13, 188, 121),
            "33": QColor(229, 229, 16),
            "34": QColor(36, 114, 200),
            "35": QColor(188, 63, 188),
            "36": QColor(17, 168, 205),
            "37": QColor(229, 229, 229),
            "90": QColor(102, 102, 102),
            "91": QColor(241, 76, 76),
            "92": QColor(35, 209, 139),
            "93": QColor(245, 245, 67),
            "94": QColor(59, 142, 234),
            "95": QColor(214, 112, 214),
            "96": QColor(41, 184, 219),
            "97": QColor(255, 255, 255),
        }

        self.bg_colors: dict[str, QColor] = {
            "40": QColor(0, 0, 0),
            "41": QColor(205, 49, 49),
            "42": QColor(13, 188, 121),
            "43": QColor(229, 229, 16),
            "44": QColor(36, 114, 200),
            "45": QColor(188, 63, 188),
            "46": QColor(17, 168, 205),
            "47": QColor(229, 229, 229),
            "100": QColor(102, 102, 102),
            "101": QColor(241, 76, 76),
            "102": QColor(35, 209, 139),
            "103": QColor(245, 245, 67),
            "104": QColor(59, 142, 234),
            "105": QColor(214, 112, 214),
            "106": QColor(41, 184, 219),
            "107": QColor(255, 255, 255),
        }

        self.current_format = QTextCharFormat()
        self.reset_format()

        self._timestamp_format = QTextCharFormat()
        self._timestamp_format.setForeground(QColor(150, 150, 150))

    def reset_format(self) -> None:
        """重置文本格式为默认"""
        self.current_format = QTextCharFormat()

    def parse_code(self, code: str) -> None:
        """解析 ANSI 转义码并更新当前格式"""
        if not code or code == "m":
            return

        code = code.rstrip("m")
        if not code:
            return

        codes = code.split(";")

        for c in codes:
            if not c:
                continue

            if c == "0":
                self.reset_format()
            elif c == "1":
                self.current_format.setFontWeight(QFont.Weight.Bold)
            elif c == "4":
                self.current_format.setFontUnderline(True)
            elif c == "7":
                fg = self.current_format.foreground().color()
                bg = self.current_format.background().color()
                self.current_format.setForeground(bg)
                self.current_format.setBackground(fg)
            elif c == "22":
                self.current_format.setFontWeight(QFont.Weight.Normal)
            elif c == "24":
                self.current_format.setFontUnderline(False)
            elif c in self.fg_colors:
                self.current_format.setForeground(self.fg_colors[c])
            elif c in self.bg_colors:
                self.current_format.setBackground(self.bg_colors[c])

    def strip_ansi(self, text: str) -> str:
        """移除文本中的 ANSI 转义序列"""
        return self.ansi_escape.sub("", text)

    def parse_text(self, text: str) -> list[tuple[str, QTextCharFormat]]:
        """解析带 ANSI 颜色的文本"""
        if not self.enabled:
            return [(self.strip_ansi(text), QTextCharFormat(self.current_format))]

        result: list[tuple[str, QTextCharFormat]] = []
        last_pos = 0

        for match in self.ansi_color_pattern.finditer(text):
            if match.start() > last_pos:
                plain_text = text[last_pos : match.start()]
                result.append((plain_text, QTextCharFormat(self.current_format)))

            self.parse_code(match.group(1) + "m")
            last_pos = match.end()

        if last_pos < len(text):
            plain_text = text[last_pos:]
            result.append((plain_text, QTextCharFormat(self.current_format)))

        return result

    def get_timestamp_format(self) -> QTextCharFormat:
        """获取时间戳的文本格式"""
        return self._timestamp_format
