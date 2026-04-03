"""
测试 core/ansi_parser.py
"""

import pytest

from core.ansi_parser import AnsiParser


class TestAnsiParser:
    def test_strip_ansi_escape(self):
        parser = AnsiParser()
        text = "\x1b[31mRed Text\x1b[0m"
        stripped = parser.strip_ansi(text)
        assert stripped == "Red Text"

    def test_strip_multiple_codes(self):
        parser = AnsiParser()
        text = "\x1b[1;31mBold Red\x1b[0m Normal"
        stripped = parser.strip_ansi(text)
        assert stripped == "Bold Red Normal"

    def test_parse_plain_text(self):
        parser = AnsiParser()
        text = "Hello World"
        result = parser.parse_text(text)
        assert len(result) == 1
        assert result[0][0] == "Hello World"

    def test_parse_with_color(self):
        parser = AnsiParser()
        text = "\x1b[31mRed\x1b[0m"
        result = parser.parse_text(text)
        assert len(result) >= 1

    def test_enabled_false(self):
        parser = AnsiParser()
        parser.enabled = False
        text = "\x1b[31mRed\x1b[0m"
        result = parser.parse_text(text)
        assert len(result) == 1
        assert result[0][0] == "Red"

    def test_reset_code(self):
        parser = AnsiParser()
        text = "\x1b[0mReset"
        result = parser.parse_text(text)
        assert len(result) >= 1
