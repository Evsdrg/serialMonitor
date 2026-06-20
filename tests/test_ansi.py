"""
测试 core/ansi.py
"""

import pytest

from core.ansi import strip_ansi


class TestStripAnsi:
    def test_plain_text_unchanged(self):
        assert strip_ansi("Hello World") == "Hello World"

    def test_simple_color_code(self):
        assert strip_ansi("\x1b[31mRed\x1b[0m") == "Red"

    def test_bold_color_code(self):
        assert strip_ansi("\x1b[1;31mBold Red\x1b[0m") == "Bold Red"

    def test_cursor_movement(self):
        assert strip_ansi("AB\x1b[2DCD") == "ABCD"

    def test_empty_string(self):
        assert strip_ansi("") == ""

    def test_only_escape_sequences(self):
        assert strip_ansi("\x1b[31m\x1b[0m") == ""

    def test_multiple_codes(self):
        text = "\x1b[31mRed\x1b[0m \x1b[32mGreen\x1b[0m"
        assert strip_ansi(text) == "Red Green"

    def test_256_color_code(self):
        text = "\x1b[38;5;123mColor\x1b[0m"
        assert strip_ansi(text) == "Color"

    def test_rgb_color_code(self):
        text = "\x1b[38;2;255;128;0mColor\x1b[0m"
        assert strip_ansi(text) == "Color"

    def test_non_csi_escape(self):
        text = "\x1b[saved\x1b[urestored"
        result = strip_ansi(text)
        assert result == "avedrestored"
