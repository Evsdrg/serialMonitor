"""
协议/数据处理辅助函数（HEX 解析、校验和等）

UI 与串口收发都会用到这些逻辑，集中在这里便于复用与测试。

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Final


_STRIP_HEX_TABLE: Final = str.maketrans("", "", " ,\t\r\n")


class ChecksumEndMode(IntEnum):
    """校验和计算结束模式。"""

    END = 0  # 末尾（无帧尾）
    MINUS_1 = 1  # 排除最后 1 字节
    MINUS_2 = 2  # 排除最后 2 字节
    MINUS_3 = 3  # 排除最后 3 字节
    MINUS_4 = 4  # 排除最后 4 字节


@dataclass(frozen=True, slots=True)
class ChecksumApplyResult:
    """校验和应用结果。"""

    payload: bytes
    checksum: int | None
    valid_range: bool


def normalize_hex_input(text: str) -> str:
    """去掉常见分隔符，得到纯 HEX 字符串。"""
    return text.translate(_STRIP_HEX_TABLE)


def parse_payload(text: str, *, is_hex: bool) -> bytes:
    """将输入文本解析为发送字节数据。

    Raises:
        ValueError: HEX 输入非法（奇数长度/非 hex 字符）。
    """
    if is_hex:
        cleaned = normalize_hex_input(text)
        if len(cleaned) % 2 != 0:
            raise ValueError("hex-odd-length")
        return bytes.fromhex(cleaned)

    return text.encode("utf-8")


def apply_checksum(
    payload: bytes,
    *,
    checksum_start_1based: int,
    checksum_end_mode: int | ChecksumEndMode = ChecksumEndMode.END,
) -> ChecksumApplyResult:
    """按 UI 规则插入校验和。

    Args:
        payload: 原始字节数据。
        checksum_start_1based: 校验起始字节（从 1 开始计数）。
        checksum_end_mode: 结束模式，见 `ChecksumEndMode`。

    Returns:
        ChecksumApplyResult 包含插入校验和后的数据。
    """
    start_idx = max(0, checksum_start_1based - 1)
    mode = ChecksumEndMode(checksum_end_mode)

    if mode == ChecksumEndMode.END:
        end_idx = len(payload)
    else:
        end_idx = len(payload) - int(mode)

    if not (start_idx < end_idx <= len(payload)):
        return ChecksumApplyResult(payload=payload, checksum=None, valid_range=False)

    checksum = sum(memoryview(payload)[start_idx:end_idx]) & 0xFF

    if mode == ChecksumEndMode.END:
        new_payload = payload + bytes([checksum])
    else:
        tail = payload[-int(mode) :]
        new_payload = payload[: -int(mode)] + bytes([checksum]) + tail

    return ChecksumApplyResult(payload=new_payload, checksum=checksum, valid_range=True)


def format_hex(data: bytes) -> str:
    """把 bytes 格式化为大写 HEX（带空格分隔）。"""
    return data.hex(" ").upper()
