#!/usr/bin/env python3
"""
Serial Monitor - A GUI-based serial terminal
串口监视器 - 基于 PyQt6 的串口调试工具

Copyright (C) 2026 cpevor
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import sys
import os
from pathlib import Path


def _resource_base() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = _resource_base()

os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.*=false;kf.*=false"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from ui.main_window import SerialMonitor
from utils.logger import setup_logging


def _suppress_stderr() -> int | None:
    """抑制 QApplication 初始化时的 QFont 警告，返回原始 stderr fd。"""
    if os.environ.get("DEBUG"):
        return None
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    os.dup2(devnull, 2)
    os.close(devnull)
    return old_stderr


def _restore_stderr(old_stderr: int | None) -> None:
    """恢复 stderr。"""
    if old_stderr is None:
        return
    os.dup2(old_stderr, 2)
    os.close(old_stderr)


def _set_app_icon(app: QApplication) -> None:
    """设置应用程序图标。"""
    icon_files = ["终端.png", "favicon.ico"]

    for directory in (BASE_DIR, Path.cwd()):
        for icon_file in icon_files:
            icon_path = directory / icon_file
            if icon_path.exists():
                try:
                    icon = QIcon(str(icon_path))
                    if not icon.isNull():
                        app.setWindowIcon(icon)
                        return
                except Exception:
                    continue


def main() -> None:
    setup_logging()

    old_stderr = _suppress_stderr()
    app = QApplication(sys.argv)
    _restore_stderr(old_stderr)

    import qdarktheme

    theme = os.environ.get("THEME", "dark")
    stylesheet = qdarktheme.load_stylesheet(theme)

    custom_style_file = BASE_DIR / "utils" / f"custom_style_{theme}.qss"
    if custom_style_file.exists():
        custom_style = custom_style_file.read_text(encoding="utf-8")
    else:
        custom_style = (BASE_DIR / "utils" / "custom_style_dark.qss").read_text(
            encoding="utf-8"
        )
    app.setStyleSheet(stylesheet + custom_style)

    app.setApplicationName("Serial Monitor")
    app.setApplicationDisplayName("Serial Monitor")
    _set_app_icon(app)

    monitor = SerialMonitor()
    monitor.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
