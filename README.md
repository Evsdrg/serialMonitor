# Serial Monitor / 串口监视器

一款基于 Python (PyQt6) 开发的轻量级桌面端串口调试工具。

## 简介 (Introduction)

本项目是一个模块化的串口终端应用，旨在为 Linux 用户提供一个现代化的串口调试界面。
主要功能包括：
*   串口参数设置（波特率、校验位等）
*   HEX / ASCII 格式的发送与接收
*   ANSI 颜色转义序列支持（彩色日志显示）
*   快捷指令面板
*   模块化设计，易于扩展

## 环境需求 (Requirements)

*   **Python 版本**: 推荐 **Python 3.12** 或更高版本。
*   **操作系统**: Linux (在 Wayland 或 X11 环境下均可运行) 、Windows

## 安装与设置 (Setup)

### 1. 创建虚拟环境 (建议)
为了保持系统环境整洁，强烈建议在项目根目录下创建一个 Python 虚拟环境：

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate
```

### 2. 安装依赖
激活虚拟环境后，通过 `requirements.txt` 安装所需库：

```bash
pip install -r requirements.txt
```

## 构建与运行 (Build & Run)

你可以直接运行源代码进行测试：
```bash
python app.py
```

### 建议打包使用
为了获得更稳定的运行体验（尤其是图标加载和窗口管理），**建议将程序打包为独立可执行文件**后使用。

本项目已包含打包配置文件 `SerialMonitor.spec`，只需运行以下命令：

```bash
pyinstaller SerialMonitor.spec
```

打包完成后，可执行程序将生成在 `dist/SerialMonitor/` 目录下。你可以直接运行该目录下的 `SerialMonitor` 文件。

## 许可证 (License)

本项目采用 **GNU General Public License v3.0 (GPLv3)** 进行许可。

Copyright (C) 2026 cpevor

这意味着如果您修改并发布了本项目，您的修改版本也必须以 GPLv3 协议开源。详细条款请参阅项目目录下的 [LICENSE](LICENSE) 文件。
