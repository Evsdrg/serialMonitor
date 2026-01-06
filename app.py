#!/usr/bin/env python3
"""
Serial Monitor - A GUI-based serial terminal for Linux
串口监视器 - 基于 PyQt6 的串口调试工具

模块化版本入口点

Copyright (C) 2026 cpevor
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""
import sys
import os

# 抑制 Qt 在 Wayland 下的警告信息
os.environ['QT_LOGGING_RULES'] = '*.debug=false;qt.qpa.*=false;kf.*=false'

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from ui.main_window import SerialMonitor

def main():
    # 抑制 QApplication 初始化时的 QFont 警告
    if not os.environ.get('DEBUG'):
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
    
    app = QApplication(sys.argv)
    
    # 恢复 stderr
    if not os.environ.get('DEBUG'):
        os.dup2(old_stderr, 2)
        os.close(old_stderr)
    
    # 设置应用程序图标
    script_dir = os.path.dirname(os.path.abspath(__file__))
    icon_files = ['终端.png', 'favicon.ico']
    
    icon_paths = [os.path.join(script_dir, icon_file) for icon_file in icon_files]
    icon_paths.extend([os.path.join(os.getcwd(), icon_file) for icon_file in icon_files])
    
    app.setApplicationName("Serial Monitor")
    app.setApplicationDisplayName("Serial Monitor")
    
    for icon_path in icon_paths:
        if os.path.exists(icon_path):
            try:
                app_icon = QIcon(icon_path)
                if not app_icon.isNull():
                    app.setWindowIcon(app_icon)
                    break
            except:
                pass
    
    monitor = SerialMonitor()
    monitor.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
