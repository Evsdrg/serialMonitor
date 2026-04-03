"""
测试 core/protocol.py 中的函数
"""

import pytest

from core.protocol import (
    normalize_hex_input,
    parse_payload,
    apply_checksum,
    format_hex,
    ChecksumEndMode,
)


class TestNormalizeHexInput:
    def test_remove_spaces(self):
        assert normalize_hex_input("AA BB CC") == "AABBCC"

    def test_remove_commas(self):
        assert normalize_hex_input("AA,BB,CC") == "AABBCC"

    def test_remove_tabs(self):
        assert normalize_hex_input("AA\tBB\tCC") == "AABBCC"

    def test_remove_newlines(self):
        assert normalize_hex_input("AA\nBB\r\nCC") == "AABBCC"

    def test_mixed_separators(self):
        assert normalize_hex_input("AA, BB\tCC\nDD") == "AABBCCDD"

    def test_no_separators(self):
        assert normalize_hex_input("AABBCC") == "AABBCC"

    def test_empty_string(self):
        assert normalize_hex_input("") == ""


class TestParsePayload:
    def test_ascii_text(self):
        assert parse_payload("Hello", is_hex=False) == b"Hello"

    def test_ascii_utf8(self):
        assert parse_payload("你好", is_hex=False) == "你好".encode("utf-8")

    def test_hex_valid(self):
        assert parse_payload("48656C6C6F", is_hex=True) == b"Hello"

    def test_hex_with_spaces(self):
        assert parse_payload("48 65 6C 6C 6F", is_hex=True) == b"Hello"

    def test_hex_odd_length_raises(self):
        with pytest.raises(ValueError, match="hex-odd-length"):
            parse_payload("48656C6C6", is_hex=True)

    def test_hex_invalid_char_raises(self):
        with pytest.raises(ValueError):
            parse_payload("GG", is_hex=True)


class TestApplyChecksum:
    def test_checksum_end_mode(self):
        payload = b"\x01\x02\x03"
        result = apply_checksum(payload, checksum_start_1based=1)
        assert result.valid_range is True
        assert result.checksum == 6
        assert result.payload == b"\x01\x02\x03\x06"

    def test_checksum_with_offset(self):
        payload = b"\x01\x02\x03\x04"
        result = apply_checksum(payload, checksum_start_1based=2)
        assert result.checksum == 9
        assert result.payload == b"\x01\x02\x03\x04\x09"

    def test_checksum_minus_1_mode(self):
        payload = b"\x01\x02\x03\xff"
        result = apply_checksum(
            payload, checksum_start_1based=1, checksum_end_mode=ChecksumEndMode.MINUS_1
        )
        assert result.checksum == 6
        assert result.payload == b"\x01\x02\x03\x06\xff"

    def test_checksum_minus_2_mode(self):
        payload = b"\x01\x02\x03\xfe\xff"
        result = apply_checksum(
            payload, checksum_start_1based=1, checksum_end_mode=ChecksumEndMode.MINUS_2
        )
        assert result.checksum == 6
        assert result.payload == b"\x01\x02\x03\x06\xfe\xff"

    def test_invalid_range(self):
        payload = b"\x01\x02"
        result = apply_checksum(payload, checksum_start_1based=10)
        assert result.valid_range is False
        assert result.checksum is None
        assert result.payload == payload

    def test_checksum_overflow(self):
        payload = b"\xff\xff\xff"
        result = apply_checksum(payload, checksum_start_1based=1)
        assert result.checksum == (0xFF + 0xFF + 0xFF) & 0xFF
        assert result.checksum == 0xFD


class TestFormatHex:
    def test_simple_bytes(self):
        assert format_hex(b"\x01\x02\x03") == "01 02 03"

    def test_empty_bytes(self):
        assert format_hex(b"") == ""

    def test_uppercase(self):
        assert format_hex(b"\xaa\xbb\xcc") == "AA BB CC"
