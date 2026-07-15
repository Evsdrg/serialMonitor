"""
国际化文本管理模块

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

from typing import Any


class I18N:
    """多语言文本管理类"""

    TEXTS: dict[str, dict[str, str]] = {
        "zh": {
            "window_title": "串口监视器",
            "port_config": "连接配置",
            "port": "端口:",
            "refresh": "刷新端口",
            "socket_host": "IP/主机:",
            "socket_port": "端口:",
            "switch_to_tcp": "TCP",
            "switch_to_serial": "串口",
            "mode_serial": "串口",
            "mode_tcp": "TCP",
            "mode_rfc2217": "RFC2217",
            "rfc2217_timeout": "协议超时:",
            "rfc2217_ignore_control": "兼容控制确认",
            "baudrate": "波特率:",
            "parity": "校验位:",
            "databits": "数据位:",
            "stopbits": "停止位:",
            "dtr": "DTR",
            "rts": "RTS",
            "connect": "连接",
            "disconnect": "断开",
            "clear_receive": "清空接收区",
            "clear_send": "清空发送区",
            "receive_mode_asc": "接收: ASCII",
            "receive_mode_hex": "接收: HEX",
            "send_mode_asc": "发送: ASCII",
            "send_mode_hex": "发送: HEX",
            "auto_scroll": "自动滚动",
            "timestamp": "显示时间",
            "ansi_colors": "彩色显示",
            "auto_reconnect": "自动连接",
            "message": "消息:",
            "send": "发送",
            "checksum": "校验和:",
            "calculate_checksum": "计算校验和",
            "lang_toggle": "English",
            "connected": "已连接到 {}",
            "disconnected": "已断开连接",
            "sent": "[已发送] {}",
            "sent_hex": "[已发送HEX] {}",
            "quick_send": "快捷发送",
            "quick_send_panel": "快捷发送面板",
            "add_item": "添加",
            "delete_item": "删除",
            "send_selected": "发送选中",
            "send_all_checked": "顺序发送",
            "stop_send": "停止发送",
            "interval": "间隔(ms):",
            "auto_checksum": "自动校验",
            "checksum_range": "第",
            "checksum_to": "字节 至",
            "edit_item": "编辑条目",
            "theme_auto": "自动",
            "theme_light": "明亮",
            "theme_dark": "暗黑",
            "item_content": "内容:",
            "item_hex_mode": "HEX模式",
            "warning": "警告",
            "error": "错误",
            "info": "提示",
            "select_port": "请选择一个端口。",
            "not_connected": "当前未连接。",
            "hex_even_chars": "十六进制数据必须有偶数个字符。",
            "invalid_hex": "无效的十六进制数据。",
            "open_port_failed": "无法打开串口:\n{}",
            "open_socket_failed": "无法连接 TCP 服务:\n{}",
            "open_rfc2217_failed": "无法建立 RFC2217 连接:\n{}",
            "enter_socket_endpoint": "请输入 IP/主机和端口。",
            "invalid_socket_port": "TCP 端口必须在 1 到 65535 之间。",
            "send_failed": "发送数据失败:\n{}",
            "device_disconnected": "设备 {} 已断开",
            "socket_disconnected": "TCP 连接 {} 已断开",
            "socket_connect_error": "TCP 连接 {} 失败: {}",
            "socket_io_error": "TCP 传输错误: {}",
            "rfc2217_disconnected": "RFC2217 连接 {} 已断开",
            "rfc2217_connect_error": "RFC2217 连接 {} 失败: {}",
            "rfc2217_io_error": "RFC2217 传输错误: {}",
            "reconnecting": "正在尝试重新连接 {}...",
            "device_found": "发现设备 {}，正在尝试连接...",
            "read_error": "读取数据时出错: {}",
            "quick_send_hex": "[快捷发送HEX] {}",
            "quick_send_ascii": "[快捷发送] {}",
            "send_error": "[错误] 发送失败: {}",
            "check_items_first": "请先勾选要发送的项目。",
            "edit": "编辑",
            "delete": "删除",
            "hex_placeholder": "输入十六进制值 (例如 AA BB CC)",
            "ascii_placeholder": "输入要发送的文字",
            "checksum_placeholder": "校验和将显示在这里",
            "ck_tag": " [CK:{:02X}]",
            "ck_invalid_range": " [CK:范围无效]",
            "trimmed_logs": "裁剪日志",
            "open_trimmed_logs_failed": "无法打开裁剪日志目录:\n{}",
            "trim_menu": "裁剪设置",
            "trim_enabled": "启用自动裁剪",
            "trim_max_lines": "最大行数",
            "trim_batch_lines": "每次裁剪行数",
            "dialog_content": "内容:",
            "dialog_hex_mode": "HEX模式",
            "dialog_auto_checksum": "自动添加校验和",
            "dialog_placeholder": "输入数据，HEX模式下用空格分隔 (如 AA BB CC)",
            "ck_end_no_tail": "末尾（无帧尾字节）",
            "ck_end_minus_1": "-1（最后1字节为帧尾）",
            "ck_end_minus_2": "-2（最后2字节为帧尾）",
            "ck_end_minus_3": "-3（最后3字节为帧尾）",
            "ck_end_minus_4": "-4（最后4字节为帧尾）",
            "line_ending": "行尾符:",
            "line_ending_none": "无",
            "line_ending_lf": "\\n (LF)",
            "line_ending_crlf": "\\r\\n (CRLF)",
            "line_ending_cr": "\\r (CR)",
            "terminal_mode_on": "终端模式",
            "terminal_mode_off": "普通模式",
            "search_placeholder": "搜索...",
            "search_prev": "上一个",
            "search_next": "下一个",
            "search_case": "区分大小写",
            "search_close": "关闭",
            "help": "使用说明",
            "help_content": """
# 使用说明

## 1. 端口配置
左上角支持本地串口、透明 TCP 和 RFC2217。串口模式下选择本地端口和串口参数；TCP 模式传输原始字节，不处理 Telnet；RFC2217 模式使用 IP/主机、端口及串口参数，并支持远程 DTR/RTS 控制。RFC2217 不提供认证和加密，只应在可信网络中使用。
- **刷新端口**：如果设备未显示，点击刷新按钮。
- **自动重连**：勾选后，若设备意外断开（非手动断开），程序会自动尝试重新连接。
- **DTR/RTS**：手动控制 DTR (Data Terminal Ready) 和 RTS (Request to Send) 信号线的电平。
  - 常用于控制单片机的复位电路（如 Arduino/ESP32 的自动下载电路）。
  - 勾选时置为有效电平，取消勾选置为无效电平。

## 2. 数据收发
- **接收模式**：
  - **ASCII**：以文本形式显示接收到的数据。
  - **HEX**：以十六进制形式显示数据（如 `41 42`）。
- **发送模式**：
  - **ASCII**：发送普通文本。
  - **HEX**：发送十六进制数据，请用空格分隔（如 `AA BB CC`）。
- **显示设置**：
  - **自动滚动**：保持视图在最底部。
  - **显示时间**：在每行数据前添加时间戳。
  - **彩色显示**：解析并显示 ANSI 转义序列颜色代码。

## 3. 校验和功能
勾选“自动校验”后，发送的数据会自动计算并附加校验和（Sum of Bytes % 256）。
- **范围**：设置从第几个字节开始计算。
- **结束**：设置计算到哪里结束（例如排除末尾的帧尾字节）。

## 4. 快捷发送面板
点击右上角的“快捷发送”按钮打开面板。
- **添加/编辑**：可以预设常用的指令，支持独立的 HEX 模式和校验和设置。
- **发送选中**：发送当前高亮的指令。
- **顺序发送**：勾选多个指令后，点击“顺序发送”，程序会按照设定的时间间隔依次发送。

## 5. 日志裁剪
为了防止长时间运行导致内存占用过高，程序默认开启日志裁剪。
- 当行数超过限制时，旧的日志会被移动到临时文件中。
- 点击“裁剪日志”按钮可以打开保存这些临时文件的文件夹。
""",
        },
        "en": {
            "window_title": "Serial Monitor",
            "port_config": "Connection Configuration",
            "port": "Port:",
            "refresh": "Refresh Ports",
            "socket_host": "IP/Host:",
            "socket_port": "Port:",
            "switch_to_tcp": "TCP",
            "switch_to_serial": "Serial",
            "mode_serial": "Serial",
            "mode_tcp": "TCP",
            "mode_rfc2217": "RFC2217",
            "rfc2217_timeout": "Protocol timeout:",
            "rfc2217_ignore_control": "Compatible control ACK",
            "baudrate": "Baudrate:",
            "parity": "Parity:",
            "databits": "Data Bits:",
            "stopbits": "Stop Bits:",
            "dtr": "DTR",
            "rts": "RTS",
            "connect": "Connect",
            "disconnect": "Disconnect",
            "clear_receive": "Clear Receive",
            "clear_send": "Clear Send",
            "receive_mode_asc": "Receive: ASCII",
            "receive_mode_hex": "Receive: HEX",
            "send_mode_asc": "Send: ASCII",
            "send_mode_hex": "Send: HEX",
            "auto_scroll": "Auto Scroll",
            "timestamp": "Timestamp",
            "ansi_colors": "ANSI Colors",
            "auto_reconnect": "Auto Connect",
            "message": "Message:",
            "send": "Send",
            "checksum": "Checksum:",
            "calculate_checksum": "Calculate Checksum",
            "lang_toggle": "中文",
            "connected": "Connected to {}",
            "disconnected": "Disconnected",
            "sent": "[Sent] {}",
            "sent_hex": "[Sent HEX] {}",
            "quick_send": "Quick Send",
            "quick_send_panel": "Quick Send Panel",
            "add_item": "Add",
            "delete_item": "Delete",
            "send_selected": "Send Selected",
            "send_all_checked": "Send Checked",
            "stop_send": "Stop",
            "interval": "Interval(ms):",
            "auto_checksum": "Auto CK",
            "checksum_range": "Byte",
            "checksum_to": "to",
            "edit_item": "Edit Item",
            "theme_auto": "Auto",
            "theme_light": "Light",
            "theme_dark": "Dark",
            "item_content": "Content:",
            "item_hex_mode": "HEX Mode",
            "warning": "Warning",
            "error": "Error",
            "info": "Info",
            "select_port": "Please select a port.",
            "not_connected": "Not connected.",
            "hex_even_chars": "Hex data must have even number of characters.",
            "invalid_hex": "Invalid hex data.",
            "open_port_failed": "Failed to open serial port:\n{}",
            "open_socket_failed": "Failed to connect to TCP service:\n{}",
            "open_rfc2217_failed": "Failed to establish RFC2217 connection:\n{}",
            "enter_socket_endpoint": "Enter an IP/host and port.",
            "invalid_socket_port": "TCP port must be between 1 and 65535.",
            "send_failed": "Failed to send data:\n{}",
            "device_disconnected": "Device {} disconnected",
            "socket_disconnected": "TCP connection {} disconnected",
            "socket_connect_error": "TCP connection {} failed: {}",
            "socket_io_error": "TCP transport error: {}",
            "rfc2217_disconnected": "RFC2217 connection {} disconnected",
            "rfc2217_connect_error": "RFC2217 connection {} failed: {}",
            "rfc2217_io_error": "RFC2217 transport error: {}",
            "reconnecting": "Attempting to reconnect to {}...",
            "device_found": "Found device {}, attempting to connect...",
            "read_error": "Error reading data: {}",
            "quick_send_hex": "[Quick HEX] {}",
            "quick_send_ascii": "[Quick Send] {}",
            "send_error": "[Error] Send failed: {}",
            "check_items_first": "Please check items to send first.",
            "edit": "Edit",
            "delete": "Delete",
            "hex_placeholder": "Enter hex values (e.g. AA BB CC)",
            "ascii_placeholder": "Enter text to send",
            "checksum_placeholder": "Checksum will appear here",
            "ck_tag": " [CK:{:02X}]",
            "ck_invalid_range": " [CK:Invalid Range]",
            "trimmed_logs": "Trim Logs",
            "open_trimmed_logs_failed": "Failed to open trim logs directory:\n{}",
            "trim_menu": "Trim Settings",
            "trim_enabled": "Enable Auto Trim",
            "trim_max_lines": "Max Lines",
            "trim_batch_lines": "Trim Batch",
            "dialog_content": "Content:",
            "dialog_hex_mode": "HEX Mode",
            "dialog_auto_checksum": "Auto Checksum",
            "dialog_placeholder": "Enter data, separate with spaces in HEX mode (e.g. AA BB CC)",
            "ck_end_no_tail": "End (no tail bytes)",
            "ck_end_minus_1": "-1 (last 1 byte is tail)",
            "ck_end_minus_2": "-2 (last 2 bytes are tail)",
            "ck_end_minus_3": "-3 (last 3 bytes are tail)",
            "ck_end_minus_4": "-4 (last 4 bytes are tail)",
            "line_ending": "Line Ending:",
            "line_ending_none": "None",
            "line_ending_lf": "\\n (LF)",
            "line_ending_crlf": "\\r\\n (CRLF)",
            "line_ending_cr": "\\r (CR)",
            "terminal_mode_on": "Terminal",
            "terminal_mode_off": "Normal",
            "search_placeholder": "Search...",
            "search_prev": "Previous",
            "search_next": "Next",
            "search_case": "Case sensitive",
            "search_close": "Close",
            "help": "Help",
            "help_content": """
# User Manual

## 1. Port Configuration
The connection area supports local Serial, transparent TCP, and RFC2217. Serial mode uses a local port and serial settings. TCP mode transfers raw bytes without Telnet processing. RFC2217 uses an IP/host, port, and serial settings with remote DTR/RTS control. RFC2217 has no authentication or encryption and should only be used on trusted networks.
- **Refresh**: Click to update the port list.
- **Auto Connect**: If enabled, the program will try to reconnect if the device is disconnected unexpectedly.
- **DTR/RTS**: Manually control DTR (Data Terminal Ready) and RTS (Request to Send) signal lines.
  - Often used to control microcontroller reset circuits (e.g., Arduino/ESP32 auto-upload circuits).
  - Checked means active level, unchecked means inactive level.

## 2. Data Transfer
- **Receive Mode**:
  - **ASCII**: Display data as text.
  - **HEX**: Display data as hex values (e.g., `41 42`).
- **Send Mode**:
  - **ASCII**: Send normal text.
  - **HEX**: Send hex values, separated by spaces (e.g., `AA BB CC`).
- **Display Settings**:
  - **Auto Scroll**: Keep the view at the bottom.
  - **Timestamp**: Show timestamp for each line.
  - **ANSI Colors**: Parse and display ANSI color codes.

## 3. Checksum
Enable "Auto Checksum" to automatically append a calculated checksum (Sum of Bytes % 256).
- **Range**: Start calculation from the Nth byte.
- **End**: Stop calculation at a specific point (e.g., excluding tail bytes).

## 4. Quick Send Panel
Click "Quick Send" to open the panel.
- **Add/Edit**: Preset frequently used commands with independent HEX/Checksum settings.
- **Send Selected**: Send the currently highlighted command.
- **Send Checked**: Send all checked commands in sequence with a specified interval.

## 5. Log Trimming
To prevent high memory usage, old logs are automatically trimmed.
- Trimmed logs are saved to temporary files.
- Click "Trim Logs" to open the folder containing these files.
""",
        },
    }

    def __init__(self, language: str = "zh") -> None:
        self.language: str = language

    @classmethod
    def get(cls, language: str, key: str, *args: Any) -> str:
        """获取翻译文本，支持格式化参数（类方法）"""
        lang_dict = cls.TEXTS.get(language) or cls.TEXTS["zh"]
        text: str = lang_dict.get(key, key)
        if args:
            return text.format(*args)
        return text

    def t(self, key: str, *args: Any) -> str:
        """获取翻译文本（实例方法）"""
        lang_dict = self.TEXTS.get(self.language) or self.TEXTS["zh"]
        text: str = lang_dict.get(key, key)
        if args:
            return text.format(*args)
        return text

    def toggle(self) -> str:
        """切换语言"""
        self.language = "en" if self.language == "zh" else "zh"
        return self.language
