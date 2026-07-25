# Serial Monitor / 串口监视器

一款基于 Python (PyQt6) 开发的轻量级桌面端串口调试工具。  
A lightweight desktop serial port debugging tool developed based on Python (PyQt6).

## 简介 (Introduction)

本项目是一个模块化的串口终端应用，旨在为 Linux 用户提供一个现代化的串口调试界面。  
This project is a modular serial-terminal application that aims to give Linux users a modern interface for serial-port debugging.

主要功能包括：  
Main features:
*   串口参数设置（波特率、校验位等）
*   Serial-port parameter configuration (baud rate, parity, etc.)
*   透明 TCP client，可连接串口服务器或网络串口桥
*   Transparent TCP client for serial servers and network serial bridges
*   RFC2217 client，支持远程串口参数和 DTR/RTS 控制
*   RFC2217 client with remote serial settings and DTR/RTS control
*   HEX / ASCII 格式的发送与接收
*   Send and receive in HEX / ASCII formats
*   ANSI 颜色转义序列支持（彩色日志显示）
*   ANSI color escape-sequence support for colored log display
*   快捷指令面板
*   Quick-command panel
*   模块化设计，易于扩展
*   Modular design for easy extension

连接模式包括本地串口、Raw TCP 和 RFC2217。Raw TCP 只传输原始字节；RFC2217 会进行 Telnet 串口控制协商。RFC2217 不提供认证和加密，只应在可信局域网、VPN 或 SSH 隧道内使用。

Connection modes include local serial, Raw TCP, and RFC2217. Raw TCP transfers bytes without protocol processing; RFC2217 negotiates remote serial settings over Telnet. RFC2217 provides no authentication or encryption and should only be used on trusted networks, VPNs, or SSH tunnels.

## 终端模式 (Terminal Mode)

点击「终端模式」按钮可在普通日志视图与终端模拟器之间切换。终端模式面向 MCU CLI、Bootloader 和 AT 命令等交互场景，键盘输入直接发送到当前连接，设备输出按字符网格渲染。

Click the "Terminal Mode" button to switch between the plain log view and the terminal emulator. Terminal mode targets interactive scenarios such as MCU CLIs, bootloaders, and AT commands: keyboard input is sent directly to the active connection and device output is rendered on a character grid.

支持的终端能力：  
Supported terminal capabilities:
*   80×24 字符网格，`\r` / `\n` / Tab / 退格、行末延迟换行与滚屏
*   80×24 character grid with CR/LF/Tab/backspace, delayed wrap and scrolling
*   CSI 光标移动与定位（`A/B/C/D/H/f`）、清行（`K`）、清屏（`J`）、光标保存/恢复（`s/u`）
*   CSI cursor movement and positioning (`A/B/C/D/H/f`), erase line (`K`), erase display (`J`), save/restore cursor (`s/u`)
*   SGR 颜色（8 色 + 亮色、256 色、真彩色）、粗体、下划线、反显与复位
*   SGR colors (8 + bright, 256-color, true color), bold, underline, reverse video and reset
*   OSC/DCS 控制字符串会被安全丢弃，UTF-8 与不完整转义序列可跨数据包正确处理
*   OSC/DCS control strings are safely discarded; UTF-8 and partial escape sequences are handled across chunks

键盘映射：  
Keyboard mapping:
*   `Ctrl+字母` → 对应控制字符（如 `Ctrl+C` 发送 ETX）
*   `Ctrl+Letter` → control character (e.g. `Ctrl+C` sends ETX)
*   `Ctrl+Shift+C` 复制选中内容；`Ctrl+Shift+V` 将剪贴板文本发送到设备（多行或超大内容需 3 秒内再次按下确认）
*   `Ctrl+Shift+C` copies the selection; `Ctrl+Shift+V` sends clipboard text to the device (multi-line or oversized content requires a second press within 3 s to confirm)
*   方向键 / Home / End / F1–F12 发送对应 ANSI 转义序列；`Ctrl+F` 打开终端内搜索
*   Arrow keys / Home / End / F1–F12 send the corresponding ANSI sequences; `Ctrl+F` opens in-terminal search

当前限制：无滚动回退缓冲，CJK 宽字符按单格处理。网格行列随窗口尺寸自适应，终端模式输出会同时写入日志裁剪管线。  
Current limitations: no scrollback buffer and CJK wide characters occupy a single cell. The grid adapts to the window size, and terminal-mode output is mirrored into the log-trimming pipeline.

## 环境需求 (Requirements)

*   **Python 版本**: 推荐 **Python 3.12** 或更高版本。
*   **Python**: 3.12 or newer recommended
*   **操作系统**: Linux (在 Wayland 或 X11 环境下均可运行) 、Windows
*   **OS**: Linux (Wayland or X11) and Windows

## 安装与设置 (Setup)

### 1. 创建虚拟环境 (Create a virtual environment)
为了保持系统环境整洁，强烈建议在项目根目录下创建一个 Python 虚拟环境：  
To maintain a clean system environment, it is strongly recommended to create a Python virtual environment in the project root directory:

```bash
# 创建虚拟环境
# Create a virtual environment
python3 -m venv .venv

# 激活虚拟环境
# Activate the virtual environment
source .venv/bin/activate
```

### 2. 安装依赖（Install dependencies）
激活虚拟环境后，通过 `requirements.txt` 安装所需库：  
After activating the virtual environment, install the required libraries using `requirements.txt`:

```bash
pip install -r requirements.txt
```

## 构建与运行 (Build & Run)

你可以直接运行源代码进行测试：  
You can directly run the source code for testing:
```bash
python app.py
```

### 建议打包使用（Suggested packaging for use）
为了获得更稳定的运行体验（尤其是图标加载和窗口管理），**建议将程序打包为独立可执行文件**后使用。  
For the best experience (icons, window handling, etc.) build a standalone executable:

本项目已包含打包配置文件 `SerialMonitor.spec`，只需运行以下命令：  
This project already includes the packaged configuration file 'serialMonitor. spec', just run the following command:

```bash
pyinstaller SerialMonitor.spec
```

打包完成后，可执行程序将生成在 `dist/SerialMonitor`。你可以直接运行该文件。
The finished bundle is `dist/SerialMonitor`; launch that executable directly.

## 许可证 (License)

本项目采用 **GNU General Public License v3.0 (GPLv3)** 进行许可。

Copyright (C) 2026 cpevor

这意味着如果您修改并发布了本项目，您的修改版本也必须以 GPLv3 协议开源。详细条款请参阅项目目录下的 [LICENSE](LICENSE) 文件。  
If you modify and distribute this program you must release your changes under GPL-3.0 as well. See the [LICENSE](LICENSE) file for the full text.
