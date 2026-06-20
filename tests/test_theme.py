"""
测试 utils/theme.py
"""

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from utils.theme import Theme, is_system_dark_mode


class TestIsSystemDarkMode:
    def test_no_app_returns_false(self):
        assert is_system_dark_mode() is False

    def test_with_app(self, qapp):
        result = is_system_dark_mode()
        assert isinstance(result, bool)


class TestThemePalettes:
    def test_get_system_palette(self, qapp):
        palette = Theme.get_system_palette()
        assert isinstance(palette, QPalette)

    def test_get_light_palette(self, qapp):
        palette = Theme.get_light_palette()
        assert isinstance(palette, QPalette)
        window_color = palette.color(QPalette.ColorRole.Window)
        assert window_color.lightness() > 200

    def test_get_dark_palette(self, qapp):
        palette = Theme.get_dark_palette()
        assert isinstance(palette, QPalette)
        window_color = palette.color(QPalette.ColorRole.Window)
        assert window_color.lightness() < 100

    def test_light_and_dark_differ(self, qapp):
        light = Theme.get_light_palette()
        dark = Theme.get_dark_palette()
        light_window = light.color(QPalette.ColorRole.Window)
        dark_window = dark.color(QPalette.ColorRole.Window)
        assert light_window != dark_window
        assert light_window.lightness() > dark_window.lightness()

    def test_light_palette_disabled_colors(self, qapp):
        palette = Theme.get_light_palette()
        disabled_text = palette.color(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text
        )
        assert isinstance(disabled_text, QColor)

    def test_dark_palette_disabled_colors(self, qapp):
        palette = Theme.get_dark_palette()
        disabled_text = palette.color(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text
        )
        assert isinstance(disabled_text, QColor)
