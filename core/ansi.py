"""
ANSI 转义序列工具函数

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

import re

_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    """移除文本中所有 ANSI 转义序列。"""
    return _ANSI_ESCAPE_RE.sub("", text)
