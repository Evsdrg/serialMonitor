"""
主窗口模块

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QPushButton, QTextEdit, QLineEdit, QLabel,
    QGroupBox, QMessageBox, QCheckBox, QSpinBox, QToolButton, QMenu, QApplication
)
from PyQt6.QtCore import QTimer, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon, QTextCursor, QTextCharFormat, QColor, QPalette

from core.ansi_parser import AnsiParser
from core.protocol import apply_checksum, format_hex, parse_payload
from core.serial_handler import SerialHandler
from ui.quick_send_manager import QuickSendManager
from ui.dialogs import HelpDialog
from utils.i18n import I18N
from utils.theme import Theme
from utils.config_manager import ConfigManager


class SerialMonitor(QMainWindow):
    """串口监视器主窗口"""

    DEFAULT_MAX_TERMINAL_LINES = 5000
    DEFAULT_TRIM_BATCH_LINES = 800
    
    def __init__(self):
        super().__init__()
        self.default_palette = QApplication.palette()
        self.serial_handler = SerialHandler()
        self.receive_hex_mode = False
        self.send_hex_mode = False
        self.auto_scroll = True
        self.show_timestamp = True
        self.auto_reconnect = False
        self.current_port = None
        self.language = 'zh'
        self.enable_ansi_colors = True
        self.quick_send_manager = QuickSendManager(self)
        self.manual_disconnect = False  # 标记是否为手动断开
        
        # 初始化 ANSI 解析器
        self.ansi_parser = AnsiParser()

        # 被裁剪日志落盘路径（tmp 下，区分 win/linux）
        self._trim_log_dir = self._get_trim_log_dir()
        self._trim_log_dir.mkdir(parents=True, exist_ok=True)
        session = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._trim_log_file = self._trim_log_dir / f"trimmed_{session}_{os.getpid()}.log"

        # 裁剪设置（下拉菜单可调）
        self._trim_enabled = True
        self._max_terminal_lines = self.DEFAULT_MAX_TERMINAL_LINES
        self._trim_batch_lines = self.DEFAULT_TRIM_BATCH_LINES

        # 串口信号绑定（后台线程读）
        self.serial_handler.data_received.connect(self._on_serial_data)
        self.serial_handler.error_occurred.connect(self._on_serial_error)
        
        self.init_ui()
        self.refresh_ports()
        self.load_settings()
        self.update_texts()

    def _get_trim_log_dir(self) -> Path:
        base = Path(tempfile.gettempdir())
        if sys.platform.startswith('win'):
            suffix = 'win'
        elif sys.platform.startswith('linux'):
            suffix = 'linux'
        else:
            suffix = 'other'
        return base / f"SerialMonitorTrimmedLogs_{suffix}"

    def _append_trimmed_log(self, text: str) -> None:
        if not text:
            return
        with self._trim_log_file.open('a', encoding='utf-8', errors='replace') as f:
            f.write(text)

    def _trim_terminal_if_needed(self) -> None:
        if not self._trim_enabled:
            return
        doc = self.terminal_display.document()
        block_count = doc.blockCount()
        if block_count <= self._max_terminal_lines:
            return

        trim_count = min(self._trim_batch_lines, max(0, block_count - self._max_terminal_lines))
        if trim_count <= 0:
            return

        # 收集将被裁剪的前 trim_count 行（plain text），落盘后再删除
        lines = []
        block = doc.firstBlock()
        for _ in range(trim_count):
            if not block.isValid():
                break
            lines.append(block.text())
            block = block.next()
        trimmed_text = "\n".join(lines) + "\n"
        self._append_trimmed_log(trimmed_text)

        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        for _ in range(trim_count):
            if not cursor.movePosition(QTextCursor.MoveOperation.NextBlock, QTextCursor.MoveMode.KeepAnchor):
                break
        cursor.removeSelectedText()
        # 移除可能残留的块分隔符
        cursor.deleteChar()
        
    def init_ui(self):
        self.setWindowTitle('串口监视器')
        self.setGeometry(100, 100, 800, 600)
        
        self.set_window_icon()
        
        # 主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 语言切换和快捷发送按钮
        lang_layout = QHBoxLayout()
        self.lang_button = QPushButton()
        self.lang_button.clicked.connect(self.toggle_language)

        # 主题选择
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([self.t('theme_auto'), self.t('theme_light'), self.t('theme_dark')])
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        self.theme_combo.setFixedWidth(80)

        # “裁剪日志”分离式按钮：左侧打开目录，右侧小按钮弹出菜单
        trim_container = QWidget()
        trim_container_layout = QHBoxLayout(trim_container)
        trim_container_layout.setContentsMargins(0, 0, 0, 0)
        trim_container_layout.setSpacing(0)

        self.trim_logs_button = QPushButton()
        self.trim_logs_button.clicked.connect(self.open_trimmed_logs_dir)

        self.trim_menu_button = QToolButton()
        self.trim_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.trim_menu_button.setArrowType(Qt.ArrowType.DownArrow)
        self.trim_menu_button.setFixedWidth(18)

        trim_container_layout.addWidget(self.trim_logs_button)
        trim_container_layout.addWidget(self.trim_menu_button)

        self.quick_send_button = QPushButton()
        self.quick_send_button.clicked.connect(self.quick_send_manager.toggle_panel)
        
        self.help_button = QPushButton()
        self.help_button.clicked.connect(self.show_help)
        
        lang_layout.addWidget(self.lang_button)
        lang_layout.addWidget(self.theme_combo)
        lang_layout.addWidget(trim_container)
        lang_layout.addStretch()
        lang_layout.addWidget(self.help_button)
        lang_layout.addWidget(self.quick_send_button)
        
        # 端口配置组
        self.port_group = QGroupBox()
        port_layout = QVBoxLayout()
        
        self.port_label = QLabel()
        self.port_combo = QComboBox()
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self.refresh_ports)
        
        self.baudrate_label = QLabel()
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems([
            "9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"
        ])
        self.baudrate_combo.setCurrentText("115200")
        
        self.parity_label = QLabel()
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["None", "Even", "Odd"])
        self.parity_combo.setCurrentText("None")
        
        self.databits_label = QLabel()
        self.databits_combo = QComboBox()
        self.databits_combo.addItems(["5", "6", "7", "8"])
        self.databits_combo.setCurrentText("8")
        
        self.stopbits_label = QLabel()
        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(["1", "1.5", "2"])
        self.stopbits_combo.setCurrentText("1")
        
        # DTR/RTS 控制
        self.dtr_checkbox = QCheckBox("DTR")
        self.dtr_checkbox.stateChanged.connect(self.toggle_dtr)
        self.rts_checkbox = QCheckBox("RTS")
        self.rts_checkbox.stateChanged.connect(self.toggle_rts)

        self.connect_button = QPushButton()
        self.connect_button.clicked.connect(self.toggle_connection)
        
        # 第一行：端口、DTR、RTS、连接
        row1 = QHBoxLayout()
        row1.addStretch()
        row1.addWidget(self.port_label)
        row1.addWidget(self.port_combo)
        row1.addWidget(self.refresh_button)
        row1.addWidget(self.dtr_checkbox)
        row1.addWidget(self.rts_checkbox)
        row1.addWidget(self.connect_button)
        row1.addStretch()
        
        # 第二行：校验位、数据位、停止位、波特率
        row2 = QHBoxLayout()
        row2.addStretch()
        row2.addWidget(self.parity_label)
        row2.addWidget(self.parity_combo)
        row2.addWidget(self.databits_label)
        row2.addWidget(self.databits_combo)
        row2.addWidget(self.stopbits_label)
        row2.addWidget(self.stopbits_combo)
        row2.addWidget(self.baudrate_label)
        row2.addWidget(self.baudrate_combo)
        row2.addStretch()
        
        port_layout.addLayout(row1)
        port_layout.addLayout(row2)
        self.port_group.setLayout(port_layout)
        
        # 终端显示区域
        self.terminal_display = QTextEdit()
        self.terminal_display.setReadOnly(True)
        
        # 控制按钮区域
        self.control_layout = QHBoxLayout()
        
        self.clear_receive_button = QPushButton()
        self.clear_receive_button.clicked.connect(self.clear_receive_area)
        
        self.clear_send_button = QPushButton()
        self.clear_send_button.clicked.connect(self.clear_send_area)
        
        self.receive_mode_button = QPushButton()
        self.receive_mode_button.clicked.connect(self.toggle_receive_mode)
        
        self.send_mode_button = QPushButton()
        self.send_mode_button.clicked.connect(self.toggle_send_mode)
        
        self.auto_scroll_checkbox = QCheckBox()
        self.auto_scroll_checkbox.setChecked(True)
        self.auto_scroll_checkbox.stateChanged.connect(self.toggle_auto_scroll)
        
        self.timestamp_checkbox = QCheckBox()
        self.timestamp_checkbox.setChecked(True)
        self.timestamp_checkbox.stateChanged.connect(self.toggle_timestamp)
        
        self.auto_reconnect_checkbox = QCheckBox()
        self.auto_reconnect_checkbox.setChecked(False)
        self.auto_reconnect_checkbox.stateChanged.connect(self.toggle_auto_reconnect)

        self.ansi_colors_checkbox = QCheckBox()
        self.ansi_colors_checkbox.setChecked(True)
        self.ansi_colors_checkbox.stateChanged.connect(self.toggle_ansi_colors)
        
        self.control_layout.addWidget(self.clear_receive_button)
        self.control_layout.addWidget(self.clear_send_button)
        self.control_layout.addWidget(self.receive_mode_button)
        self.control_layout.addWidget(self.send_mode_button)
        self.control_layout.addWidget(self.auto_scroll_checkbox)
        self.control_layout.addWidget(self.timestamp_checkbox)
        self.control_layout.addWidget(self.ansi_colors_checkbox)
        self.control_layout.addWidget(self.auto_reconnect_checkbox)
        self.control_layout.addStretch()
        
        # 发送区域
        self.send_layout = QHBoxLayout()
        self.message_label = QLabel()
        self.send_input = QLineEdit()
        self.send_input.returnPressed.connect(self.send_data)
        self.send_button = QPushButton()
        self.send_button.clicked.connect(self.send_data)
        
        # 行尾符下拉框
        self.line_ending_label = QLabel()
        self.line_ending_combo = QComboBox()
        self.line_ending_combo.addItems(['', '\n', '\r\n', '\r'])  # 值
        self.line_ending_combo.setFixedWidth(120)
        
        self.send_layout.addWidget(self.message_label)
        self.send_layout.addWidget(self.send_input, 4)
        self.send_layout.addWidget(self.line_ending_label)
        self.send_layout.addWidget(self.line_ending_combo)
        self.send_layout.addWidget(self.send_button)
        
        # 校验和区域
        self.checksum_layout = QHBoxLayout()
        
        # 自动添加校验和复选框
        self.auto_checksum_checkbox = QCheckBox()
        self.auto_checksum_checkbox.setChecked(False)
        
        # 校验范围设置
        self.checksum_range_label = QLabel()
        self.checksum_start_spinbox = QSpinBox()
        self.checksum_start_spinbox.setRange(1, 9999)
        self.checksum_start_spinbox.setValue(1)
        self.checksum_start_spinbox.setFixedWidth(60)
        
        self.checksum_to_label = QLabel()
        
        self.checksum_end_combo = QComboBox()
        # 下拉选项会在 update_texts 中设置
        
        # 校验和结果显示
        self.checksum_label = QLabel()
        self.checksum_input = QLineEdit()
        self.checksum_input.setPlaceholderText("")
        self.checksum_input.setReadOnly(True)
        self.checksum_input.setFixedWidth(100)
        self.calculate_checksum_button = QPushButton()
        self.calculate_checksum_button.clicked.connect(self.calculate_checksum)
        
        self.checksum_layout.addWidget(self.auto_checksum_checkbox)
        self.checksum_layout.addWidget(self.checksum_range_label)
        self.checksum_layout.addWidget(self.checksum_start_spinbox)
        self.checksum_layout.addWidget(self.checksum_to_label)
        self.checksum_layout.addWidget(self.checksum_end_combo)
        self.checksum_layout.addWidget(self.checksum_label)
        self.checksum_layout.addWidget(self.checksum_input)
        self.checksum_layout.addWidget(self.calculate_checksum_button)
        self.checksum_layout.addStretch()
        
        # 添加到主布局
        main_layout.addLayout(lang_layout)
        main_layout.addWidget(self.port_group)
        main_layout.addWidget(self.terminal_display)
        main_layout.addLayout(self.control_layout)
        main_layout.addLayout(self.send_layout)
        main_layout.addLayout(self.checksum_layout)
        
        # 串口读取定时器
        # read_timer 已移除：改用 SerialHandler 后台线程读取
        
        # 设备连接检测定时器
        self.device_check_timer = QTimer()
        self.device_check_timer.timeout.connect(self.check_device_connection)
        self.device_check_timer.start(1000)
        
    def set_window_icon(self):
        """设置窗口图标"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # 向上两级到项目根目录
        project_dir = os.path.dirname(os.path.dirname(script_dir))
        
        icon_files = ['终端.png', 'favicon.ico']
        
        icon_paths = [os.path.join(project_dir, icon_file) for icon_file in icon_files]
        icon_paths.extend([os.path.join(os.getcwd(), icon_file) for icon_file in icon_files])
        
        for icon_path in icon_paths:
            if os.path.exists(icon_path):
                try:
                    icon = QIcon(icon_path)
                    if not icon.isNull():
                        self.setWindowIcon(icon)
                        break
                except:
                    continue
    
    def toggle_language(self):
        """切换语言"""
        self.language = 'en' if self.language == 'zh' else 'zh'
        self.update_texts()

    def change_theme(self, index):
        """切换主题"""
        app = QApplication.instance()
        if index == 1: # Light
            app.setPalette(Theme.get_light_palette())
        elif index == 2: # Dark
            app.setPalette(Theme.get_dark_palette())
        else: # Auto (index 0)
            app.setPalette(self.default_palette)
            app.setPalette(self.default_palette)
        
    def t(self, key):
        """获取当前语言的文本"""
        return I18N.get(self.language, key)
    
    def update_texts(self):
        """更新所有界面文本"""
        
        # 更新主题下拉框文本
        current_theme_idx = self.theme_combo.currentIndex()
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItems([self.t('theme_auto'), self.t('theme_light'), self.t('theme_dark')])
        self.theme_combo.setCurrentIndex(current_theme_idx)
        self.theme_combo.blockSignals(False)

        self.setWindowTitle(self.t('window_title'))
        self.port_group.setTitle(self.t('port_config'))
        self.port_label.setText(self.t('port'))
        self.refresh_button.setText(self.t('refresh'))
        self.baudrate_label.setText(self.t('baudrate'))
        self.parity_label.setText(self.t('parity'))
        self.databits_label.setText(self.t('databits'))
        self.stopbits_label.setText(self.t('stopbits'))
        self.dtr_checkbox.setText(self.t('dtr'))
        self.rts_checkbox.setText(self.t('rts'))
        
        if self.serial_handler.is_open():
            self.connect_button.setText(self.t('disconnect'))
        else:
            self.connect_button.setText(self.t('connect'))
        
        self.clear_receive_button.setText(self.t('clear_receive'))
        self.clear_send_button.setText(self.t('clear_send'))
        
        mode_text_receive = self.t('receive_mode_hex') if self.receive_hex_mode else self.t('receive_mode_asc')
        self.receive_mode_button.setText(mode_text_receive)
        
        mode_text_send = self.t('send_mode_hex') if self.send_hex_mode else self.t('send_mode_asc')
        self.send_mode_button.setText(mode_text_send)
        
        self.auto_scroll_checkbox.setText(self.t('auto_scroll'))
        self.timestamp_checkbox.setText(self.t('timestamp'))
        self.ansi_colors_checkbox.setText(self.t('ansi_colors'))
        self.auto_reconnect_checkbox.setText(self.t('auto_reconnect'))
        
        self.message_label.setText(self.t('message'))
        self.send_button.setText(self.t('send'))
        
        # 更新行尾符下拉框
        current_ending_idx = self.line_ending_combo.currentIndex()
        self.line_ending_combo.blockSignals(True)
        self.line_ending_combo.clear()
        self.line_ending_combo.addItem(self.t('line_ending_none'), '')
        self.line_ending_combo.addItem(self.t('line_ending_lf'), '\n')
        self.line_ending_combo.addItem(self.t('line_ending_crlf'), '\r\n')
        self.line_ending_combo.addItem(self.t('line_ending_cr'), '\r')
        self.line_ending_combo.setCurrentIndex(current_ending_idx)
        self.line_ending_combo.blockSignals(False)
        self.line_ending_label.setText(self.t('line_ending'))
        
        # 校验和相关文本
        self.auto_checksum_checkbox.setText(self.t('auto_checksum'))
        self.checksum_range_label.setText(self.t('checksum_range'))
        self.checksum_to_label.setText(self.t('checksum_to'))
        
        # 更新校验范围下拉框选项
        current_idx = self.checksum_end_combo.currentIndex()
        self.checksum_end_combo.clear()
        if self.language == 'zh':
            self.checksum_end_combo.addItems([
                "末尾（无帧尾）",
                "-1（1字节帧尾）",
                "-2（2字节帧尾）",
                "-3（3字节帧尾）",
                "-4（4字节帧尾）"
            ])
        else:
            self.checksum_end_combo.addItems([
                "End (no tail)",
                "-1 (1B tail)",
                "-2 (2B tail)",
                "-3 (3B tail)",
                "-4 (4B tail)"
            ])
        if current_idx >= 0:
            self.checksum_end_combo.setCurrentIndex(current_idx)
        
        self.checksum_label.setText(self.t('checksum'))
        self.calculate_checksum_button.setText(self.t('calculate_checksum'))
        
        self.lang_button.setText(self.t('lang_toggle'))
        self.trim_logs_button.setText(self.t('trimmed_logs'))
        self.quick_send_button.setText(self.t('quick_send'))
        self.help_button.setText(self.t('help'))

        self._rebuild_trim_menu()
        
        # 更新快捷发送面板文本
        self.quick_send_manager.update_language(self.language)
        
        # 更新占位符文本
        placeholder = self.t('hex_placeholder') if self.send_hex_mode else self.t('ascii_placeholder')
        self.send_input.setPlaceholderText(placeholder)
        
        self.checksum_input.setPlaceholderText(self.t('checksum_placeholder'))

    def open_trimmed_logs_dir(self):
        """打开裁剪日志目录"""
        try:
            self._trim_log_dir.mkdir(parents=True, exist_ok=True)
            ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._trim_log_dir)))
            if not ok:
                raise RuntimeError(str(self._trim_log_dir))
        except Exception as e:
            QMessageBox.critical(self, self.t('error'), self.t('open_trimmed_logs_failed').format(str(e)))

    def show_help(self):
        """显示使用说明"""
        dialog = HelpDialog(self, language=self.language)
        dialog.exec()

    def _rebuild_trim_menu(self):
        menu = QMenu(self)

        enabled_action = menu.addAction(self.t('trim_enabled'))
        enabled_action.setCheckable(True)
        enabled_action.setChecked(self._trim_enabled)
        enabled_action.toggled.connect(self._set_trim_enabled)

        menu.addSeparator()

        max_lines_menu = menu.addMenu(self.t('trim_max_lines'))
        for value in (1000, 5000, 20000):
            action = max_lines_menu.addAction(str(value))
            action.setCheckable(True)
            action.setChecked(self._max_terminal_lines == value)
            action.triggered.connect(lambda _=False, v=value: self._set_max_terminal_lines(v))

        batch_menu = menu.addMenu(self.t('trim_batch_lines'))
        for value in (200, 800, 2000):
            action = batch_menu.addAction(str(value))
            action.setCheckable(True)
            action.setChecked(self._trim_batch_lines == value)
            action.triggered.connect(lambda _=False, v=value: self._set_trim_batch_lines(v))

        self.trim_menu_button.setMenu(menu)

    def _set_trim_enabled(self, enabled: bool):
        self._trim_enabled = bool(enabled)

    def _set_max_terminal_lines(self, value: int):
        self._max_terminal_lines = int(value)
        self._rebuild_trim_menu()
        self._trim_terminal_if_needed()

    def _set_trim_batch_lines(self, value: int):
        self._trim_batch_lines = int(value)
        self._rebuild_trim_menu()
            
    def refresh_ports(self):
        """刷新可用端口列表"""
        self.port_combo.clear()
        for port in self.serial_handler.get_available_ports():
            self.port_combo.addItem(port)
            
    def toggle_connection(self):
        """切换串口连接状态"""
        if self.serial_handler.is_open():
            self.manual_disconnect = True
            self.close_serial()
        else:
            self.open_serial()
            
    def open_serial(self):
        """打开串口"""
        if self.serial_handler.is_open():
            return
            
        self.manual_disconnect = False
        port = self.port_combo.currentText()
        if not port:
            QMessageBox.warning(self, self.t('warning'), self.t('select_port'))
            return
            
        ok = self.serial_handler.open(
            port=port,
            baudrate=self.baudrate_combo.currentText(),
            parity=self.parity_combo.currentText(),
            databits=self.databits_combo.currentText(),
            stopbits=self.stopbits_combo.currentText(),
        )
        if not ok:
            QMessageBox.critical(
                self, self.t('error'), self.t('open_port_failed').format(self.serial_handler.last_error or '')
            )
            return

        self.current_port = port
        
        # 应用当前的 DTR/RTS 状态
        self.serial_handler.set_dtr(self.dtr_checkbox.isChecked())
        self.serial_handler.set_rts(self.rts_checkbox.isChecked())
        
        self.append_to_terminal(self.t('connected').format(port) + '\n', with_timestamp=True)
        self.update_texts()
            
    def close_serial(self, silent=False, device_lost=False):
        """关闭串口"""
        if self.serial_handler.is_open():
            self.serial_handler.close()

        if not silent:
            if device_lost:
                msg = self.t('device_disconnected').format(self.current_port) + '\n'
            else:
                msg = self.t('disconnected') + '\n'
            self.append_to_terminal(msg, with_timestamp=True)

        self.update_texts()
            
    def get_timestamp(self):
        """获取当前时间戳"""
        return datetime.now().strftime('[%H:%M:%S.%f')[:-3] + '] '
    
    def append_to_terminal(self, text, with_timestamp=True):
        """向终端追加文本"""
        current_cursor = self.terminal_display.textCursor()
        has_selection = current_cursor.hasSelection()
        
        end_cursor = QTextCursor(self.terminal_display.document())
        end_cursor.movePosition(QTextCursor.MoveOperation.End)
        self.terminal_display.setTextCursor(end_cursor)

        cursor = self.terminal_display.textCursor()
        cursor.beginEditBlock()
        if with_timestamp and self.show_timestamp:
            cursor.insertText(self.get_timestamp(), self.ansi_parser.get_timestamp_format())

        self.append_text_with_ansi(text)
        cursor.endEditBlock()

        self._trim_terminal_if_needed()
        
        if has_selection:
            self.terminal_display.setTextCursor(current_cursor)
        elif self.auto_scroll:
            self.terminal_display.moveCursor(QTextCursor.MoveOperation.End)
    
    def append_text_with_ansi(self, text):
        """解析并显示带 ANSI 颜色的文本"""
        if not self.enable_ansi_colors:
            clean_text = self.ansi_parser.strip_ansi(text)
            self.terminal_display.insertPlainText(clean_text)
            return
        
        segments = self.ansi_parser.parse_text(text)
        
        cursor = self.terminal_display.textCursor()
        for segment_text, format_obj in segments:
            cursor.insertText(segment_text, format_obj)
    
    def _on_serial_data(self, data: bytes):
        """串口线程收到数据（UI线程槽函数）"""
        if not data:
            return
        if self.receive_hex_mode:
            text = format_hex(data) + '\n'
        else:
            text = data.decode('utf-8', errors='backslashreplace')
            if not text.endswith('\n'):
                text += '\n'
        self.append_to_terminal(text, with_timestamp=True)

    def _on_serial_error(self, message: str):
        # SerialHandler 内部会 close，这里仅提示
        self.append_to_terminal(self.t('read_error').format(message) + '\n', with_timestamp=True)
                
    def send_data(self):
        """发送数据"""
        if not self.serial_handler.is_open():
            QMessageBox.warning(self, self.t('warning'), self.t('not_connected'))
            return
            
        data = self.send_input.text()
        if not data:
            return
        
        # 获取校验和设置
        auto_checksum = self.auto_checksum_checkbox.isChecked()
        checksum_start = self.checksum_start_spinbox.value()
        checksum_end_mode = self.checksum_end_combo.currentIndex()
            
        try:
            byte_values = parse_payload(data, is_hex=self.send_hex_mode)
        except ValueError as e:
            if str(e) == 'hex-odd-length':
                QMessageBox.warning(self, self.t('warning'), self.t('hex_even_chars'))
            else:
                QMessageBox.warning(self, self.t('warning'), self.t('invalid_hex'))
            return

        # 添加行尾符
        line_ending = self.line_ending_combo.currentData()
        if line_ending:
            byte_values += line_ending.encode('utf-8')

        display_data = data
        if auto_checksum:
            res = apply_checksum(
                byte_values,
                checksum_start_1based=checksum_start,
                checksum_end_mode=checksum_end_mode,
            )
            byte_values = res.payload
            if res.valid_range and res.checksum is not None:
                display_data += self.t('ck_tag').format(res.checksum)
            else:
                display_data += self.t('ck_invalid_range')

        try:
            if not self.serial_handler.write_data(byte_values):
                raise RuntimeError(self.serial_handler.last_error or 'write failed')

            sent_key = 'sent_hex' if self.send_hex_mode else 'sent'
            self.append_to_terminal(self.t(sent_key).format(display_data) + '\n', with_timestamp=True)
            self.send_input.clear()
        except Exception as e:
            QMessageBox.critical(self, self.t('error'), self.t('send_failed').format(str(e)))
            
    def clear_receive_area(self):
        """清空接收区"""
        self.terminal_display.clear()
        
    def clear_send_area(self):
        """清空发送区"""
        self.send_input.clear()
        
    def toggle_receive_mode(self):
        """切换接收模式"""
        self.receive_hex_mode = not self.receive_hex_mode
        self.receive_mode_button.setText(self.t('receive_mode_hex') if self.receive_hex_mode else self.t('receive_mode_asc'))
        
    def toggle_send_mode(self):
        """切换发送模式"""
        self.send_hex_mode = not self.send_hex_mode
        self.send_mode_button.setText(self.t('send_mode_hex') if self.send_hex_mode else self.t('send_mode_asc'))
        self.send_input.setPlaceholderText(self.t('hex_placeholder') if self.send_hex_mode else self.t('ascii_placeholder'))
        self.update_texts()
            
    def toggle_auto_scroll(self):
        """切换自动滚动"""
        self.auto_scroll = self.auto_scroll_checkbox.isChecked()
    
    def toggle_timestamp(self):
        """切换时间戳显示"""
        self.show_timestamp = self.timestamp_checkbox.isChecked()

    def toggle_ansi_colors(self):
        """切换彩色显示"""
        self.enable_ansi_colors = self.ansi_colors_checkbox.isChecked()
    
    def toggle_auto_reconnect(self):
        """切换自动重连"""
        self.auto_reconnect = self.auto_reconnect_checkbox.isChecked()

    def toggle_dtr(self):
        """切换 DTR 状态"""
        self.serial_handler.set_dtr(self.dtr_checkbox.isChecked())

    def toggle_rts(self):
        """切换 RTS 状态"""
        self.serial_handler.set_rts(self.rts_checkbox.isChecked())
    
    def get_available_ports(self):
        """获取可用端口列表"""
        return self.serial_handler.get_available_ports()
    
    def check_device_connection(self):
        """检查设备连接状态"""
        available_ports = self.get_available_ports()
        
        if self.serial_handler.is_open() and self.current_port:
            if self.current_port not in available_ports:
                self.close_serial(silent=False, device_lost=True)
        
        if self.auto_reconnect and (not self.serial_handler.is_open()) and (not self.manual_disconnect):
            if self.current_port and self.current_port in available_ports:
                self.append_to_terminal(self.t('reconnecting').format(self.current_port) + '\n', with_timestamp=True)
                
                index = self.port_combo.findText(self.current_port)
                if index >= 0:
                    self.port_combo.setCurrentIndex(index)
                self.open_serial()
            elif available_ports:
                for port in available_ports:
                    if 'ttyUSB' in port or 'ttyACM' in port:
                        self.append_to_terminal(self.t('device_found').format(port) + '\n', with_timestamp=True)
                        
                        self.refresh_ports()
                        index = self.port_combo.findText(port)
                        if index >= 0:
                            self.port_combo.setCurrentIndex(index)
                        self.current_port = port
                        self.open_serial()
                        break
        
    def calculate_checksum(self):
        """计算校验和"""
        data = self.send_input.text()
        if not data:
            self.checksum_input.clear()
            return
            
        try:
            try:
                byte_values = parse_payload(data, is_hex=self.send_hex_mode)
            except ValueError:
                self.checksum_input.setText(self.t('invalid_hex'))
                return

            checksum = sum(byte_values) & 0xFF
            self.checksum_input.setText(f"{checksum:02X} (0x{checksum:02X})")
        except:
            self.checksum_input.setText(self.t('error'))

    def load_settings(self):
        """加载应用设置"""
        settings = ConfigManager.load_settings()
        
        # 窗口几何信息
        if 'geometry' in settings:
            self.restoreGeometry(bytes.fromhex(settings['geometry']))
            
        # 语言
        self.language = settings.get('language', 'zh')
        
        # 主题
        theme_idx = settings.get('theme_index', 0)
        self.theme_combo.setCurrentIndex(theme_idx)
        
        # 串口设置
        self.baudrate_combo.setCurrentText(settings.get('baudrate', '115200'))
        self.parity_combo.setCurrentText(settings.get('parity', 'None'))
        self.databits_combo.setCurrentText(settings.get('databits', '8'))
        self.stopbits_combo.setCurrentText(settings.get('stopbits', '1'))
        
        # 显示设置
        self.receive_hex_mode = settings.get('receive_hex_mode', False)
        self.send_hex_mode = settings.get('send_hex_mode', False)
        self.auto_scroll = settings.get('auto_scroll', True)
        self.show_timestamp = settings.get('show_timestamp', True)
        self.enable_ansi_colors = settings.get('enable_ansi_colors', True)
        self.auto_reconnect = settings.get('auto_reconnect', False)
        
        # 更新UI控件状态
        self.auto_scroll_checkbox.setChecked(self.auto_scroll)
        self.timestamp_checkbox.setChecked(self.show_timestamp)
        self.ansi_colors_checkbox.setChecked(self.enable_ansi_colors)
        self.auto_reconnect_checkbox.setChecked(self.auto_reconnect)
        
        # 校验和设置
        self.auto_checksum_checkbox.setChecked(settings.get('auto_checksum', False))
        self.checksum_start_spinbox.setValue(settings.get('checksum_start', 1))
        self.checksum_end_combo.setCurrentIndex(settings.get('checksum_end_mode', 0))
        
        # DTR/RTS
        self.dtr_checkbox.setChecked(settings.get('dtr_state', False))
        self.rts_checkbox.setChecked(settings.get('rts_state', False))
        
        # 裁剪设置
        self._trim_enabled = settings.get('trim_enabled', True)
        self._max_terminal_lines = settings.get('max_terminal_lines', self.DEFAULT_MAX_TERMINAL_LINES)
        self._trim_batch_lines = settings.get('trim_batch_lines', self.DEFAULT_TRIM_BATCH_LINES)
        self._rebuild_trim_menu()

    def save_settings(self):
        """保存应用设置"""
        settings = {
            'geometry': self.saveGeometry().data().hex(),
            'language': self.language,
            'theme_index': self.theme_combo.currentIndex(),
            'baudrate': self.baudrate_combo.currentText(),
            'parity': self.parity_combo.currentText(),
            'databits': self.databits_combo.currentText(),
            'stopbits': self.stopbits_combo.currentText(),
            'receive_hex_mode': self.receive_hex_mode,
            'send_hex_mode': self.send_hex_mode,
            'auto_scroll': self.auto_scroll,
            'show_timestamp': self.show_timestamp,
            'enable_ansi_colors': self.enable_ansi_colors,
            'auto_reconnect': self.auto_reconnect,
            'auto_checksum': self.auto_checksum_checkbox.isChecked(),
            'checksum_start': self.checksum_start_spinbox.value(),
            'checksum_end_mode': self.checksum_end_combo.currentIndex(),
            'dtr_state': self.dtr_checkbox.isChecked(),
            'rts_state': self.rts_checkbox.isChecked(),
            'trim_enabled': self._trim_enabled,
            'max_terminal_lines': self._max_terminal_lines,
            'trim_batch_lines': self._trim_batch_lines
        }
        ConfigManager.save_settings(settings)
        
        # 保存快捷发送列表
        self.quick_send_manager.save_settings()
            
    def closeEvent(self, event):
        """处理窗口关闭事件"""
        self.save_settings()
        self.device_check_timer.stop()
        self.close_serial(silent=True)
        # 关闭快捷发送窗口
        self.quick_send_manager.close()
        event.accept()
