"""
主题颜色配置管理

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication


def is_system_dark_mode() -> bool:
    """检测系统是否为暗色模式。"""
    app = QApplication.instance()
    if app is None:
        return False
    palette = app.palette()
    window_bg = palette.color(QPalette.ColorRole.Window)
    window_text = palette.color(QPalette.ColorRole.WindowText)
    return window_bg.lightness() < window_text.lightness()


class Theme:
    """主题颜色配置管理"""

    @staticmethod
    def get_system_palette() -> QPalette:
        """获取系统默认调色板（跟随系统暗色/亮色模式）。"""
        app = QApplication.instance()
        if app is None:
            return QPalette()
        return app.style().standardPalette()

    @staticmethod
    def get_light_palette() -> QPalette:
        """获取明亮主题调色板"""
        palette = QPalette()

        palette.setColor(QPalette.ColorRole.Window, QColor(237, 237, 237))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(228, 228, 228))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.Text, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.Button, QColor(224, 224, 224))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(150, 150, 150))
        palette.setColor(QPalette.ColorRole.Light, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Midlight, QColor(240, 240, 240))
        palette.setColor(QPalette.ColorRole.Mid, QColor(180, 180, 180))
        palette.setColor(QPalette.ColorRole.Dark, QColor(140, 140, 140))
        palette.setColor(QPalette.ColorRole.Shadow, QColor(80, 80, 80))

        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.WindowText,
            QColor(128, 128, 128),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Text,
            QColor(128, 128, 128),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.ButtonText,
            QColor(128, 128, 128),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Highlight,
            QColor(200, 200, 200),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.HighlightedText,
            QColor(128, 128, 128),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.PlaceholderText,
            QColor(200, 200, 200),
        )

        return palette

    @staticmethod
    def get_dark_palette() -> QPalette:
        """获取暗黑主题调色板"""
        palette = QPalette()

        palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 50, 50))
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(128, 128, 128))
        palette.setColor(QPalette.ColorRole.Light, QColor(80, 80, 80))
        palette.setColor(QPalette.ColorRole.Midlight, QColor(66, 66, 66))
        palette.setColor(QPalette.ColorRole.Mid, QColor(42, 42, 42))
        palette.setColor(QPalette.ColorRole.Dark, QColor(26, 26, 26))
        palette.setColor(QPalette.ColorRole.Shadow, QColor(13, 13, 13))

        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.WindowText,
            QColor(100, 100, 100),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Text,
            QColor(100, 100, 100),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.ButtonText,
            QColor(100, 100, 100),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Highlight,
            QColor(80, 80, 80),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.HighlightedText,
            QColor(100, 100, 100),
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.PlaceholderText,
            QColor(80, 80, 80),
        )

        return palette
