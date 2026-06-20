import pytest
"""
core/protocol.py 的属性测试

使用 hypothesis 自动生成测试输入，验证协议层函数的不变式。
"""

import string

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from core.protocol import (
    ChecksumEndMode,
    apply_checksum,
    format_hex,
    normalize_hex_input,
    parse_payload,
)


# ── 共享策略 ─────────────────────────────────────────────


HEX_CHARS = "0123456789abcdefABCDEF"
hex_char = st.sampled_from(HEX_CHARS)


@st.composite
def hex_strings(draw, min_size: int = 0, max_size: int = 64) -> str:
    """生成偶数长度的 hex 字符串。"""
    n = draw(st.integers(min_value=min_size, max_value=max_size // 2)) * 2
    return "".join(draw(st.lists(hex_char, min_size=n, max_size=n)))


@st.composite
def hex_strings_with_separators(draw, min_size: int = 0, max_size: int = 64) -> str:
    """生成带空格/逗号/制表符分隔的 hex 字符串。"""
    n = draw(st.integers(min_value=min_size, max_value=max_size // 2))
    parts = []
    for i in range(n):
        if i > 0 and draw(st.booleans()):
            parts.append(draw(st.sampled_from([" ", ",", "\t"])))
        parts.append(draw(st.lists(hex_char, min_size=2, max_size=2)))
    return "".join("".join(p) if isinstance(p, list) else p for p in parts)


@st.composite
def ascii_strings(draw, min_size: int = 0, max_size: int = 256) -> str:
    """生成 ASCII 可打印字符串。"""
    return draw(st.text(
        alphabet=string.ascii_letters + string.digits + string.punctuation + " \r\n",
        min_size=min_size,
        max_size=max_size,
    ))


# ── normalize_hex_input 属性测试 ─────────────────────────


class TestNormalizeHexInput:
    @given(hex_strings(min_size=0, max_size=64))
    def test_idempotent(self, s: str) -> None:
        """normalize 应该是幂等的。"""
        once = normalize_hex_input(s)
        twice = normalize_hex_input(once)
        assert once == twice

    @given(hex_strings_with_separators(min_size=0, max_size=64))
    def test_separators_removed(self, s: str) -> None:
        """分隔符（空格/逗号/制表符）应被全部移除。"""
        result = normalize_hex_input(s)
        assert " " not in result
        assert "," not in result
        assert "\t" not in result
        assert "\r" not in result
        assert "\n" not in result

    @given(hex_strings(min_size=0, max_size=64))
    def test_output_only_hex_chars(self, s: str) -> None:
        """输出应只含 hex 字符。"""
        result = normalize_hex_input(s)
        assert all(c in HEX_CHARS for c in result)

    @given(hex_strings(min_size=0, max_size=64))
    def test_no_separators_unchanged(self, s: str) -> None:
        """无分隔符时输入应等于输出。"""
        assert normalize_hex_input(s) == s

    @given(hex_strings(min_size=0, max_size=64))
    def test_length_preserved_when_no_separators(self, s: str) -> None:
        """无分隔符时长度不变。"""
        assert len(normalize_hex_input(s)) == len(s)

    @given(hex_strings(min_size=0, max_size=32))
    def test_case_preserved(self, s: str) -> None:
        """结果保持原 hex 串大小写（不主动转换）。"""
        assert normalize_hex_input(s.lower()) == s.lower()
        assert normalize_hex_input(s.upper()) == s.upper()


# ── parse_payload 属性测试 ──────────────────────────────


class TestParsePayload:
    @given(hex_strings(min_size=0, max_size=64))
    def test_hex_valid_even_length(self, s: str) -> None:
        """偶数长度 hex 串应能解析。"""
        result = parse_payload(s, is_hex=True)
        assert isinstance(result, bytes)
        assert len(result) == len(s) // 2

    @given(ascii_strings(min_size=0, max_size=128))
    def test_ascii_round_trip(self, s: str) -> None:
        """ASCII 解析后 encode 应该一致。"""
        result = parse_payload(s, is_hex=False)
        assert result == s.encode("utf-8")

    @given(st.integers(min_value=1, max_value=64))
    def test_hex_odd_length_raises(self, n: int) -> None:
        """奇数长度 hex 应抛 ValueError。"""
        odd_hex = "A" * (n * 2 + 1)
        try:
            parse_payload(odd_hex, is_hex=True)
            assert False, "should have raised"
        except ValueError:
            pass

    @given(hex_strings(min_size=0, max_size=64))
    def test_hex_with_separators(self, s: str) -> None:
        """带分隔符的 hex 串应解析为相同字节。"""
        with_sep = " ".join(s[i:i+2] for i in range(0, len(s), 2))
        assert parse_payload(with_sep, is_hex=True) == parse_payload(s, is_hex=True)

    @given(hex_strings(min_size=2, max_size=32))
    def test_format_parse_round_trip(self, s: str) -> None:
        """format_hex → parse_payload 应能还原。"""
        data = parse_payload(s, is_hex=True)
        formatted = format_hex(data)
        reparsed = parse_payload(formatted, is_hex=True)
        assert reparsed == data


# ── format_hex 属性测试 ─────────────────────────────────


class TestFormatHex:
    @given(st.binary(min_size=0, max_size=128))
    def test_uppercase(self, data: bytes) -> None:
        """输出应全为大写。"""
        result = format_hex(data)
        assert result == result.upper()

    @given(st.binary(min_size=0, max_size=128))
    def test_only_hex_and_space(self, data: bytes) -> None:
        """输出应只含 hex 字符和空格。"""
        result = format_hex(data)
        for c in result:
            assert c in HEX_CHARS or c == " "

    @given(st.binary(min_size=0, max_size=128))
    def test_length_property(self, data: bytes) -> None:
        """长度 = 3n - 1（n bytes，每 byte 2 hex + 1 空格，最后无空格）。"""
        result = format_hex(data)
        if len(data) == 0:
            assert result == ""
        else:
            # 3n - 1 形式：每 byte 占 3 字符（HEX HEX SPACE），最后一个无 SPACE
            assert len(result) == 3 * len(data) - 1

    @given(st.binary(min_size=0, max_size=64))
    def test_format_parse_round_trip(self, data: bytes) -> None:
        """format → parse 应还原。"""
        formatted = format_hex(data)
        parsed = parse_payload(formatted, is_hex=True)
        assert parsed == data

    @given(st.binary(min_size=1, max_size=64))
    def test_pairs_split_by_space(self, data: bytes) -> None:
        """每 2 个 hex 字符后接一个空格。"""
        result = format_hex(data)
        parts = result.split(" ")
        assert len(parts) == len(data)
        for part, byte in zip(parts, data):
            assert len(part) == 2
            assert int(part, 16) == byte


# ── apply_checksum 属性测试 ──────────────────────────────


class TestApplyChecksum:
    @given(
        st.binary(min_size=0, max_size=64),
        st.integers(min_value=1, max_value=10),
    )
    def test_checksum_in_byte_range(self, payload: bytes, start: int) -> None:
        """校验和值应在 0-255 范围内。"""
        assume(start <= len(payload) + 1)
        result = apply_checksum(payload, checksum_start_1based=start)
        if result.checksum is not None:
            assert 0 <= result.checksum <= 255

    @given(
        st.binary(min_size=1, max_size=64),
        st.integers(min_value=1, max_value=10),
    )
    def test_end_mode_adds_one_byte(self, payload: bytes, start: int) -> None:
        """END 模式下应增加 1 字节。"""
        assume(start <= len(payload))
        result = apply_checksum(payload, checksum_start_1based=start)
        assert len(result.payload) == len(payload) + 1

    @given(
        st.binary(min_size=5, max_size=64),
        st.integers(min_value=1, max_value=5),
        st.sampled_from([ChecksumEndMode.MINUS_1, ChecksumEndMode.MINUS_2,
                         ChecksumEndMode.MINUS_3, ChecksumEndMode.MINUS_4]),
    )
    def test_minus_n_mode_adds_one_byte(self, payload: bytes, start: int, mode: ChecksumEndMode) -> None:
        """MINUS_N 模式下：
        - 有效时长度 +1（checksum 插入在 tail 前）
        - 无效时返回原 payload
        """
        result = apply_checksum(
            payload, checksum_start_1based=start, checksum_end_mode=mode
        )
        if result.valid_range:
            assert len(result.payload) == len(payload) + 1
        else:
            assert result.payload == payload

    @given(
        st.binary(min_size=5, max_size=64),
        st.integers(min_value=1, max_value=5),
        st.sampled_from([ChecksumEndMode.MINUS_1, ChecksumEndMode.MINUS_2,
                         ChecksumEndMode.MINUS_3, ChecksumEndMode.MINUS_4]),
    )
    def test_minus_n_mode_preserves_tail(self, payload: bytes, start: int, mode: ChecksumEndMode) -> None:
        """MINUS_N 模式有效时，最后 int(mode) 字节应保持不变。"""
        result = apply_checksum(
            payload, checksum_start_1based=start, checksum_end_mode=mode
        )
        if result.valid_range:
            tail_size = int(mode)
            assert result.payload[-tail_size:] == payload[-tail_size:]

    @given(
        st.binary(min_size=1, max_size=64),
        st.integers(min_value=1, max_value=10),
    )
    def test_start_beyond_end_invalid(self, payload: bytes, start: int) -> None:
        """start 超过 payload 长度应返回 valid_range=False。"""
        result = apply_checksum(payload, checksum_start_1based=start)
        if start > len(payload):
            assert result.valid_range is False
            assert result.checksum is None

    @given(
        st.binary(min_size=2, max_size=64),
        st.integers(min_value=1, max_value=3),
    )
    def test_checksum_sums_correctly(self, payload: bytes, start: int) -> None:
        """校验和应等于 payload[start-1:end] 之和 mod 256。"""
        assume(start <= len(payload))
        result = apply_checksum(payload, checksum_start_1based=start)
        if result.valid_range:
            expected = sum(payload[start - 1:]) & 0xFF
            assert result.checksum == expected

    @given(
        st.binary(min_size=4, max_size=64),
        st.integers(min_value=1, max_value=4),
    )
    def test_minus_1_checksum_preserves_tail(self, payload: bytes, start: int) -> None:
        """MINUS_1 模式下最后 1 字节应保留。"""
        assume(start <= len(payload) - 1)
        result = apply_checksum(
            payload, checksum_start_1based=start,
            checksum_end_mode=ChecksumEndMode.MINUS_1,
        )
        if result.valid_range:
            assert result.payload[-1] == payload[-1]

    @given(
        st.binary(min_size=0, max_size=64),
        st.integers(min_value=1, max_value=10),
    )
    def test_idempotent_structure(self, payload: bytes, start: int) -> None:
        """连续应用不应改变 valid_range 判定。"""
        assume(start <= len(payload) + 1)
        r1 = apply_checksum(payload, checksum_start_1based=start)
        # 对 r1.payload 再次应用，valid_range 应一致
        # （仅在 END 模式下有意义）
        r2 = apply_checksum(r1.payload, checksum_start_1based=start)
        # r2 的 payload 必然更长（r1 加了 1 字节），所以 r1.checksum 不为空时
        # r2 应该也能 valid
        if r1.valid_range and r1.checksum is not None:
            assert r2.valid_range


# ── 跨函数组合属性测试 ─────────────────────────────────


class TestProtocolRoundTrip:
    @given(st.binary(min_size=0, max_size=64))
    def test_hex_round_trip(self, data: bytes) -> None:
        """format_hex → parse_payload → data。"""
        formatted = format_hex(data)
        parsed = parse_payload(formatted, is_hex=True)
        assert parsed == data

    @given(ascii_strings(min_size=0, max_size=128))
    def test_ascii_send_then_format(self, text: str) -> None:
        """ASCII 文本 parse 后，hex 格式化应能还原（前提是文本全 ASCII）。"""
        data = parse_payload(text, is_hex=False)
        # 重新 format
        formatted = format_hex(data)
        # 再 parse
        parsed = parse_payload(formatted, is_hex=True)
        assert parsed == data

    @given(hex_strings(min_size=4, max_size=32), st.integers(min_value=1, max_value=3))
    def test_checksum_validates_payload(self, hex_str: str, start: int) -> None:
        """对 hex 串计算校验和后，结果 payload 应包含原数据 + 1 字节。"""
        assume(start <= len(hex_str) // 2)
        data = parse_payload(hex_str, is_hex=True)
        result = apply_checksum(data, checksum_start_1based=start)
        if result.valid_range:
            # 前 len(data) 字节应等于原数据
            assert result.payload[:len(data)] == data
            # 最后一个字节是校验和
            assert result.payload[-1] == result.checksum
