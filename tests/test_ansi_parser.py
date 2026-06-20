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

    def test_bold_format(self):
        parser = AnsiParser()
        result = parser.parse_text("\x1b[1mBold\x1b[0m")
        bold_seg = [seg for seg in result if seg[0] == "Bold"]
        assert len(bold_seg) == 1
        assert bold_seg[0][1].fontWeight() == 700

    def test_underline_format(self):
        parser = AnsiParser()
        result = parser.parse_text("\x1b[4mUnderlined\x1b[0m")
        ul_seg = [seg for seg in result if seg[0] == "Underlined"]
        assert len(ul_seg) == 1
        assert ul_seg[0][1].fontUnderline() is True

    def test_bold_then_normal(self):
        parser = AnsiParser()
        parser.parse_text("\x1b[1mBold\x1b[22mNormal")
        assert parser.current_format.fontWeight() == parser.current_format.font().Weight.Normal

    def test_underline_then_off(self):
        parser = AnsiParser()
        parser.parse_text("\x1b[4mUnder\x1b[24mNormal")
        assert parser.current_format.fontUnderline() is False

    def test_reverse_video(self):
        parser = AnsiParser()
        parser.parse_text("\x1b[7mReversed")

    def test_unknown_code_ignored(self):
        parser = AnsiParser()
        result = parser.parse_text("\x1b[99mText")
        assert len(result) == 1
        assert result[0][0] == "Text"

    def test_empty_color_code(self):
        parser = AnsiParser()
        result = parser.parse_text("\x1b[mText")
        assert len(result) == 1
        assert result[0][0] == "Text"

    def test_multiple_segments(self):
        parser = AnsiParser()
        result = parser.parse_text("\x1b[31mRed\x1b[0m \x1b[32mGreen")
        texts = [seg[0] for seg in result]
        assert "Red" in texts
        assert "Green" in texts

    def test_timestamp_format(self):
        parser = AnsiParser()
        fmt = parser.get_timestamp_format()
        assert fmt is not None

    def test_setup_reinitializes(self):
        parser = AnsiParser()
        parser.parse_text("\x1b[31mRed")
        parser.setup()
        assert parser.current_format.foreground().color().red() == 0


class TestAnsiParserEdgeCases:
    def test_parse_code_empty(self):
        parser = AnsiParser()
        parser.parse_code("")
        # 不抛异常，格式不变

    def test_parse_code_just_m(self):
        parser = AnsiParser()
        parser.parse_code("m")
        # 不抛异常，格式不变

    def test_parse_code_empty_after_rstrip(self):
        parser = AnsiParser()
        parser.parse_code(";m")
        # 空 code 应被忽略

    def test_parse_code_empty_in_split(self):
        parser = AnsiParser()
        parser.parse_code("1;;4m")
        # 中间空 code 应被忽略
        assert parser.current_format.fontWeight() == 700
        assert parser.current_format.fontUnderline() is True

    def test_parse_code_bg_color(self):
        parser = AnsiParser()
        parser.parse_code("41m")
        # 背景色 41 = red
        bg = parser.current_format.background().color()
        assert bg.red() > 0

    def test_parse_code_22_resets_bold(self):
        parser = AnsiParser()
        parser.parse_code("1m")
        assert parser.current_format.fontWeight() == 700
        parser.parse_code("22m")
        assert parser.current_format.fontWeight() == 400

    def test_parse_code_24_resets_underline(self):
        parser = AnsiParser()
        parser.parse_code("4m")
        assert parser.current_format.fontUnderline() is True
        parser.parse_code("24m")
        assert parser.current_format.fontUnderline() is False

    def test_parse_code_7_reverses(self):
        parser = AnsiParser()
        fg = parser.current_format.foreground().color()
        bg = parser.current_format.background().color()
        parser.parse_code("7m")
        new_fg = parser.current_format.foreground().color()
        new_bg = parser.current_format.background().color()
        # fg 和 bg 应交换
        assert new_fg == bg
        assert new_bg == fg

    def test_strip_ansi_with_text(self):
        parser = AnsiParser()
        text = "Hello \x1b[31mRed\x1b[0m World"
        assert parser.strip_ansi(text) == "Hello Red World"

    def test_parse_text_only_escape(self):
        parser = AnsiParser()
        result = parser.parse_text("\x1b[31m")
        # 末尾的转义码不应被解析为可见字符
        assert all(seg[0] == "" for seg in result) or len(result) == 1
