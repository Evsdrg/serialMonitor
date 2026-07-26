"""
测试 core/ansi_parser.py
"""

from PyQt6.QtGui import QColor, QTextFormat

import pytest
from PyQt6.QtCore import Qt

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
        result = parser.parse_text("\x1b[31mRed\x1b[mText")
        text_segment = next(segment for segment in result if segment[0] == "Text")
        assert text_segment[1].foreground().style() == Qt.BrushStyle.NoBrush

    def test_default_foreground_and_background_codes(self):
        parser = AnsiParser()
        parser.parse_code("31;42m")
        parser.parse_code("39;49m")

        assert parser.current_format.foreground().style() == Qt.BrushStyle.NoBrush
        assert parser.current_format.background().style() == Qt.BrushStyle.NoBrush

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

    def test_parse_code_27_disables_reverse(self):
        parser = AnsiParser()
        parser.parse_code("31;42m")
        original_fg = parser.current_format.foreground()
        original_bg = parser.current_format.background()
        parser.parse_code("7m")
        parser.parse_code("27m")

        assert parser.current_format.foreground() == original_fg
        assert parser.current_format.background() == original_bg

    def test_strip_ansi_with_text(self):
        parser = AnsiParser()
        text = "Hello \x1b[31mRed\x1b[0m World"
        assert parser.strip_ansi(text) == "Hello Red World"

    def test_parse_text_only_escape(self):
        parser = AnsiParser()
        result = parser.parse_text("\x1b[31m")
        # 末尾的转义码不应被解析为可见字符
        assert all(seg[0] == "" for seg in result) or len(result) == 1


class TestAnsiParserExtendedColors:
    def test_256_color_foreground_cube(self):
        parser = AnsiParser()
        parser.parse_code("38;5;196m")
        assert parser.current_format.foreground().color() == QColor(255, 0, 0)

    def test_256_color_background_cube(self):
        parser = AnsiParser()
        parser.parse_code("48;5;21m")
        assert parser.current_format.background().color() == QColor(0, 0, 255)

    def test_256_color_standard_matches_base_palette(self):
        parser = AnsiParser()
        parser.parse_code("38;5;1m")
        assert parser.current_format.foreground().color() == QColor(205, 49, 49)

    def test_256_color_bright_matches_base_palette(self):
        parser = AnsiParser()
        parser.parse_code("38;5;9m")
        assert parser.current_format.foreground().color() == QColor(241, 76, 76)

    def test_256_color_grayscale(self):
        parser = AnsiParser()
        parser.parse_code("38;5;232m")
        assert parser.current_format.foreground().color() == QColor(8, 8, 8)

    def test_truecolor_foreground(self):
        parser = AnsiParser()
        parser.parse_code("38;2;12;34;56m")
        assert parser.current_format.foreground().color() == QColor(12, 34, 56)

    def test_truecolor_background(self):
        parser = AnsiParser()
        parser.parse_code("48;2;200;100;50m")
        assert parser.current_format.background().color() == QColor(200, 100, 50)

    def test_malformed_extended_sequence_ignored(self):
        from PyQt6.QtGui import QTextFormat

        parser = AnsiParser()
        parser.parse_code("38;5m")
        parser.parse_code("38;2;10m")
        assert not parser.current_format.hasProperty(
            QTextFormat.Property.ForegroundBrush
        )

    def test_extended_color_in_parse_text(self):
        parser = AnsiParser()
        segments = parser.parse_text("\x1b[38;5;196mred")
        assert segments[-1][0] == "red"
        assert segments[-1][1].foreground().color() == QColor(255, 0, 0)


class TestZeroPaddedAndControlStrings:
    """P1: 零填充 SGR 参数与非 SGR 控制串"""

    def test_zero_padded_sgr_applies_color(self):
        parser = AnsiParser()
        parser.parse_code("01;31m")
        fmt = parser.current_format
        assert fmt.foreground().color() == QColor(205, 49, 49)

    def test_zero_padded_reset_clears_format(self):
        parser = AnsiParser()
        parser.parse_code("31m")
        parser.parse_code("00m")
        fmt = parser.current_format
        assert not fmt.hasProperty(QTextFormat.Property.ForegroundBrush)

    def test_osc_sequence_is_not_rendered(self):
        parser = AnsiParser()
        segments = parser.parse_text("\x1b]0;window title\x07hello")
        assert "".join(s[0] for s in segments) == "hello"

    def test_non_sgr_csi_is_not_rendered(self):
        parser = AnsiParser()
        segments = parser.parse_text("\x1b[2Khello")
        assert "".join(s[0] for s in segments) == "hello"


class TestExtendedColorEdgeCases:
    def test_truecolor_components_clamped(self):
        parser = AnsiParser()
        parser.parse_code("38;2;999;-5;0m")
        fmt = parser.current_format
        assert fmt.foreground().color() == QColor(255, 0, 0)

    def test_truncated_truecolor_sequence_ignored(self):
        parser = AnsiParser()
        parser.parse_code("38;2;30;40m")
        fmt = parser.current_format
        assert not fmt.hasProperty(QTextFormat.Property.ForegroundBrush)
        assert not fmt.hasProperty(QTextFormat.Property.BackgroundBrush)

    def test_truncated_256_sequence_ignored(self):
        parser = AnsiParser()
        parser.parse_code("38;5m")
        fmt = parser.current_format
        assert not fmt.hasProperty(QTextFormat.Property.ForegroundBrush)
