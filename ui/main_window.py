"""
主窗口模块

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QPushButton,
    QTextEdit,
    QLineEdit,
    QLabel,
    QGroupBox,
    QMessageBox,
    QCheckBox,
    QSpinBox,
    QToolButton,
    QMenu,
    QApplication,
)
from PyQt6.QtCore import QTimer, Qt, QUrl
from PyQt6.QtGui import (
    QDesktopServices,
    QIcon,
    QKeySequence,
    QShortcut,
    QTextCursor,
    QTextCharFormat,
    QTextDocument,
    QColor,
    QPalette,
    QAction,
)

from core.ansi_parser import AnsiParser
from core.protocol import apply_checksum, format_hex, parse_payload
from core.serial_handler import SerialHandler
from ui.quick_send_manager import QuickSendManager
from ui.dialogs import HelpDialog
from ui.terminal_emulator import TerminalEmulator
from ui.search_bar import SearchBar
from utils.i18n import I18N
from utils.theme import Theme, is_system_dark_mode
from utils.config_manager import ConfigManager
import qdarktheme

logger = logging.getLogger(__name__)


def _resource_base() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _resource_base()


class TerminalTrimManager:
    """终端日志裁剪管理器。

    当终端行数超过阈值时，将旧内容写入临时日志文件并从终端移除。
    """

    DEFAULT_MAX_LINES = 5000
    DEFAULT_BATCH_LINES = 800

    def __init__(self) -> None:
        self.enabled: bool = True
        self.max_lines: int = self.DEFAULT_MAX_LINES
        self.batch_lines: int = self.DEFAULT_BATCH_LINES

        self._log_dir = self._get_log_dir()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        session = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_file = self._log_dir / f"trimmed_{session}_{os.getpid()}.log"

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    def _get_log_dir(self) -> Path:
        base = Path(tempfile.gettempdir())
        if sys.platform.startswith("win"):
            suffix = "win"
        elif sys.platform.startswith("linux"):
            suffix = "linux"
        else:
            suffix = "other"
        return base / f"SerialMonitorTrimmedLogs_{suffix}"

    def _append_log(self, text: str) -> None:
        if not text:
            return
        try:
            with self._log_file.open("a", encoding="utf-8", errors="replace") as f:
                f.write(text)
        except OSError as e:
            logger.warning("Failed to write trim log: %s", e)

    def trim_if_needed(self, document: QTextDocument) -> None:
        """检查并裁剪文档内容。"""
        if not self.enabled:
            return

        block_count = document.blockCount()
        if block_count <= self.max_lines:
            return

        trim_count = min(self.batch_lines, max(0, block_count - self.max_lines))
        if trim_count <= 0:
            return

        lines: list[str] = []
        block = document.firstBlock()
        for _ in range(trim_count):
            if not block.isValid():
                break
            lines.append(block.text())
            block = block.next()

        trimmed_text = "\n".join(lines) + "\n"
        self._append_log(trimmed_text)

        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        for _ in range(trim_count):
            if not cursor.movePosition(
                QTextCursor.MoveOperation.NextBlock, QTextCursor.MoveMode.KeepAnchor
            ):
                break
        cursor.removeSelectedText()
        cursor.deleteChar()

    def to_dict(self) -> dict[str, Any]:
        return {
            "trim_enabled": self.enabled,
            "max_terminal_lines": self.max_lines,
            "trim_batch_lines": self.batch_lines,
        }

    def load_from_dict(self, data: dict[str, Any]) -> None:
        self.enabled = data.get("trim_enabled", True)
        self.max_lines = data.get("max_terminal_lines", self.DEFAULT_MAX_LINES)
        self.batch_lines = data.get("trim_batch_lines", self.DEFAULT_BATCH_LINES)


class SerialMonitor(QMainWindow):
    """串口监视器主窗口"""

    def __init__(self) -> None:
        super().__init__()
        self.default_palette = QApplication.palette()
        self.serial_handler = SerialHandler()
        self.receive_hex_mode: bool = False
        self.send_hex_mode: bool = False
        self.auto_scroll: bool = True
        self.show_timestamp: bool = True
        self.auto_reconnect: bool = False
        self.current_port: Optional[str] = None
        self.language: str = "zh"
        self.enable_ansi_colors: bool = True
        self.quick_send_manager = QuickSendManager(self)
        self.manual_disconnect: bool = False
        self.terminal_mode: bool = False
        self.current_theme: str = "dark" if is_system_dark_mode() else "light"

        self.ansi_parser = AnsiParser()
        self.trim_manager = TerminalTrimManager()

        # 串口信号绑定
        self.serial_handler.data_received.connect(self._on_serial_data)
        self.serial_handler.error_occurred.connect(self._on_serial_error)

        self.init_ui()
        self.refresh_ports()
        self.load_settings()
        self.update_texts()

    # ── UI 构建 ──────────────────────────────────────────────

    def init_ui(self) -> None:
        self.setWindowTitle("串口监视器")
        self.setGeometry(100, 100, 800, 600)
        self.set_window_icon()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # ── 顶部工具栏 ──
        toolbar_layout = QHBoxLayout()

        self.lang_button = QPushButton()
        self.lang_button.clicked.connect(self.toggle_language)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(
            [self.t("theme_auto"), self.t("theme_light"), self.t("theme_dark")]
        )
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        self.theme_combo.setFixedWidth(80)

        # 裁剪日志按钮
        trim_container = QWidget()
        trim_layout = QHBoxLayout(trim_container)
        trim_layout.setContentsMargins(0, 0, 0, 0)
        trim_layout.setSpacing(0)
        self.trim_logs_button = QPushButton()
        self.trim_logs_button.clicked.connect(self.open_trimmed_logs_dir)
        self.trim_menu_button = QToolButton()
        self.trim_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.trim_menu_button.setArrowType(Qt.ArrowType.DownArrow)
        self.trim_menu_button.setFixedSize(20, 24)
        trim_layout.addWidget(self.trim_logs_button)
        trim_layout.addWidget(self.trim_menu_button)

        self.quick_send_button = QPushButton()
        self.quick_send_button.clicked.connect(self.quick_send_manager.toggle_panel)
        self.help_button = QPushButton()
        self.help_button.clicked.connect(self.show_help)

        toolbar_layout.addWidget(self.lang_button)
        toolbar_layout.addWidget(self.theme_combo)
        toolbar_layout.addWidget(trim_container)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.help_button)
        toolbar_layout.addWidget(self.quick_send_button)

        # ── 端口配置组 ──
        self.port_group = QGroupBox()
        port_layout = QVBoxLayout()

        self.port_label = QLabel()
        self.port_combo = QComboBox()
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self.refresh_ports)

        self.baudrate_label = QLabel()
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(
            ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
        )
        self.baudrate_combo.setCurrentText("115200")

        self.parity_label = QLabel()
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["None", "Even", "Odd"])

        self.databits_label = QLabel()
        self.databits_combo = QComboBox()
        self.databits_combo.addItems(["5", "6", "7", "8"])
        self.databits_combo.setCurrentText("8")

        self.stopbits_label = QLabel()
        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(["1", "1.5", "2"])

        self.dtr_checkbox = QCheckBox("DTR")
        self.dtr_checkbox.stateChanged.connect(self.toggle_dtr)
        self.rts_checkbox = QCheckBox("RTS")
        self.rts_checkbox.stateChanged.connect(self.toggle_rts)

        self.connect_button = QPushButton()
        self.connect_button.clicked.connect(self.toggle_connection)

        row1 = QHBoxLayout()
        row1.addStretch()
        row1.addWidget(self.port_label)
        row1.addWidget(self.port_combo)
        row1.addWidget(self.refresh_button)
        row1.addWidget(self.dtr_checkbox)
        row1.addWidget(self.rts_checkbox)
        row1.addWidget(self.connect_button)
        row1.addStretch()

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

        # ── 终端显示区域（普通模式） ──
        self.terminal_display = QTextEdit()
        self.terminal_display.setReadOnly(True)

        # ── 终端模拟器（终端模式） ──
        self.terminal_emulator = TerminalEmulator(rows=24, cols=80)
        self.terminal_emulator.hide()
        self.terminal_emulator.key_pressed.connect(self._on_terminal_key)

        # ── 搜索栏 ──
        self.search_bar = SearchBar(self)
        self.search_bar.search_requested.connect(self._do_search)
        self.search_bar.close_requested.connect(self._close_search)

        # ── 控制按钮区域 ──
        ctrl_layout = QHBoxLayout()

        self.terminal_mode_button = QPushButton()
        self.terminal_mode_button.setCheckable(True)
        self.terminal_mode_button.clicked.connect(self.toggle_terminal_mode)

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

        ctrl_layout.addWidget(self.terminal_mode_button)
        for w in (
            self.clear_receive_button,
            self.clear_send_button,
            self.receive_mode_button,
            self.send_mode_button,
            self.auto_scroll_checkbox,
            self.timestamp_checkbox,
            self.ansi_colors_checkbox,
            self.auto_reconnect_checkbox,
        ):
            ctrl_layout.addWidget(w)
        ctrl_layout.addStretch()

        # ── 发送区域 ──
        self._send_area_widgets: list = []

        send_layout = QHBoxLayout()
        self.message_label = QLabel()
        self.send_input = QLineEdit()
        self.send_input.returnPressed.connect(self.send_data)
        self.send_button = QPushButton()
        self.send_button.clicked.connect(self.send_data)

        self.line_ending_label = QLabel()
        self.line_ending_combo = QComboBox()
        self.line_ending_combo.addItems(["", "\n", "\r\n", "\r"])
        self.line_ending_combo.setFixedWidth(120)

        send_layout.addWidget(self.message_label)
        send_layout.addWidget(self.send_input, 4)
        send_layout.addWidget(self.line_ending_label)
        send_layout.addWidget(self.line_ending_combo)
        send_layout.addWidget(self.send_button)

        self._send_area_widgets = [
            self.message_label,
            self.send_input,
            self.line_ending_label,
            self.line_ending_combo,
            self.send_button,
        ]

        # ── 校验和区域 ──
        self._checksum_area_widgets: list = []

        ck_layout = QHBoxLayout()
        self.auto_checksum_checkbox = QCheckBox()
        self.checksum_range_label = QLabel()
        self.checksum_start_spinbox = QSpinBox()
        self.checksum_start_spinbox.setRange(1, 9999)
        self.checksum_start_spinbox.setValue(1)
        self.checksum_start_spinbox.setFixedWidth(60)
        self.checksum_to_label = QLabel()
        self.checksum_end_combo = QComboBox()
        self.checksum_label = QLabel()
        self.checksum_input = QLineEdit()
        self.checksum_input.setReadOnly(True)
        self.checksum_input.setFixedWidth(160)
        self.calculate_checksum_button = QPushButton()
        self.calculate_checksum_button.clicked.connect(self.calculate_checksum)

        for w in (
            self.auto_checksum_checkbox,
            self.checksum_range_label,
            self.checksum_start_spinbox,
            self.checksum_to_label,
            self.checksum_end_combo,
            self.checksum_label,
            self.checksum_input,
            self.calculate_checksum_button,
        ):
            ck_layout.addWidget(w)
        ck_layout.addStretch()

        self._checksum_area_widgets = [
            self.auto_checksum_checkbox,
            self.checksum_range_label,
            self.checksum_start_spinbox,
            self.checksum_to_label,
            self.checksum_end_combo,
            self.checksum_label,
            self.checksum_input,
            self.calculate_checksum_button,
        ]

        # ── 组装主布局 ──
        main_layout.addLayout(toolbar_layout)
        main_layout.addWidget(self.port_group)
        main_layout.addWidget(self.terminal_display)
        main_layout.addWidget(self.terminal_emulator)
        main_layout.addWidget(self.search_bar)
        main_layout.addLayout(ctrl_layout)
        main_layout.addLayout(send_layout)
        main_layout.addLayout(ck_layout)

        # Ctrl+F 搜索快捷键
        find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        find_shortcut.activated.connect(self._open_search)

        # 设备连接检测定时器
        self.device_check_timer = QTimer()
        self.device_check_timer.timeout.connect(self.check_device_connection)
        self.device_check_timer.start(1000)

    # ── 图标 ────────────────────────────────────────────────

    def set_window_icon(self) -> None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.dirname(os.path.dirname(script_dir))
        icon_files = ["终端.png", "favicon.ico"]
        search_dirs = [project_dir, os.getcwd()]

        for directory in search_dirs:
            for icon_file in icon_files:
                icon_path = os.path.join(directory, icon_file)
                if os.path.exists(icon_path):
                    try:
                        icon = QIcon(icon_path)
                        if not icon.isNull():
                            self.setWindowIcon(icon)
                            return
                    except Exception:
                        continue

    # ── i18n 与主题 ─────────────────────────────────────────

    def t(self, key: str, *args: Any) -> str:
        return I18N.get(self.language, key, *args) or key

    def toggle_language(self) -> None:
        self.language = "en" if self.language == "zh" else "zh"
        self.update_texts()

    def change_theme(self, index: int) -> None:
        app = QApplication.instance()
        if app is None:
            return

        if index == 0:
            theme = "dark" if is_system_dark_mode() else "light"
        elif index == 1:
            theme = "light"
        else:
            theme = "dark"

        self.current_theme = theme
        stylesheet = qdarktheme.load_stylesheet(theme)
        custom_style_file = BASE_DIR / "utils" / f"custom_style_{theme}.qss"
        if custom_style_file.exists():
            custom_style = custom_style_file.read_text(encoding="utf-8")
        else:
            custom_style = (BASE_DIR / "utils" / "custom_style_dark.qss").read_text(
                encoding="utf-8"
            )
        app.setStyleSheet(stylesheet + custom_style)
        self._rebuild_trim_menu()

    def update_texts(self) -> None:
        # 更新主题下拉框文本
        idx = self.theme_combo.currentIndex()
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItems(
            [self.t("theme_auto"), self.t("theme_light"), self.t("theme_dark")]
        )
        self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.blockSignals(False)

        self.setWindowTitle(self.t("window_title"))
        self.port_group.setTitle(self.t("port_config"))
        self.port_label.setText(self.t("port"))
        self.refresh_button.setText(self.t("refresh"))
        self.baudrate_label.setText(self.t("baudrate"))
        self.parity_label.setText(self.t("parity"))
        self.databits_label.setText(self.t("databits"))
        self.stopbits_label.setText(self.t("stopbits"))
        self.dtr_checkbox.setText(self.t("dtr"))
        self.rts_checkbox.setText(self.t("rts"))

        self.connect_button.setText(
            self.t("disconnect") if self.serial_handler.is_open() else self.t("connect")
        )

        self.terminal_mode_button.setText(
            self.t("terminal_mode_off")
            if self.terminal_mode
            else self.t("terminal_mode_on")
        )
        self.clear_receive_button.setText(self.t("clear_receive"))
        self.clear_send_button.setText(self.t("clear_send"))
        self.receive_mode_button.setText(
            self.t("receive_mode_hex")
            if self.receive_hex_mode
            else self.t("receive_mode_asc")
        )
        self.send_mode_button.setText(
            self.t("send_mode_hex") if self.send_hex_mode else self.t("send_mode_asc")
        )

        self.auto_scroll_checkbox.setText(self.t("auto_scroll"))
        self.timestamp_checkbox.setText(self.t("timestamp"))
        self.ansi_colors_checkbox.setText(self.t("ansi_colors"))
        self.auto_reconnect_checkbox.setText(self.t("auto_reconnect"))
        self.message_label.setText(self.t("message"))
        self.send_button.setText(self.t("send"))

        # 行尾符
        end_idx = self.line_ending_combo.currentIndex()
        self.line_ending_combo.blockSignals(True)
        self.line_ending_combo.clear()
        self.line_ending_combo.addItem(self.t("line_ending_none"), "")
        self.line_ending_combo.addItem(self.t("line_ending_lf"), "\n")
        self.line_ending_combo.addItem(self.t("line_ending_crlf"), "\r\n")
        self.line_ending_combo.addItem(self.t("line_ending_cr"), "\r")
        self.line_ending_combo.setCurrentIndex(end_idx)
        self.line_ending_combo.blockSignals(False)
        self.line_ending_label.setText(self.t("line_ending"))

        # 校验和
        self.auto_checksum_checkbox.setText(self.t("auto_checksum"))
        self.checksum_range_label.setText(self.t("checksum_range"))
        self.checksum_to_label.setText(self.t("checksum_to"))

        ck_idx = self.checksum_end_combo.currentIndex()
        self.checksum_end_combo.clear()
        if self.language == "zh":
            self.checksum_end_combo.addItems(
                [
                    "末尾（无帧尾）",
                    "-1（1字节帧尾）",
                    "-2（2字节帧尾）",
                    "-3（3字节帧尾）",
                    "-4（4字节帧尾）",
                ]
            )
        else:
            self.checksum_end_combo.addItems(
                [
                    "End (no tail)",
                    "-1 (1B tail)",
                    "-2 (2B tail)",
                    "-3 (3B tail)",
                    "-4 (4B tail)",
                ]
            )
        if ck_idx >= 0:
            self.checksum_end_combo.setCurrentIndex(ck_idx)

        self.checksum_label.setText(self.t("checksum"))
        self.calculate_checksum_button.setText(self.t("calculate_checksum"))
        self.lang_button.setText(self.t("lang_toggle"))
        self.trim_logs_button.setText(self.t("trimmed_logs"))
        self.quick_send_button.setText(self.t("quick_send"))
        self.help_button.setText(self.t("help"))

        self._rebuild_trim_menu()
        self.quick_send_manager.update_language(self.language)
        self.search_bar.update_language(
            {
                "search_placeholder": self.t("search_placeholder"),
                "search_prev": self.t("search_prev"),
                "search_next": self.t("search_next"),
                "search_case": self.t("search_case"),
                "search_close": self.t("search_close"),
            }
        )

        self.send_input.setPlaceholderText(
            self.t("hex_placeholder")
            if self.send_hex_mode
            else self.t("ascii_placeholder")
        )
        self.checksum_input.setPlaceholderText(self.t("checksum_placeholder"))

    # ── 裁剪菜单 ────────────────────────────────────────────

    def _rebuild_trim_menu(self) -> None:
        menu = QMenu(self)
        app = QApplication.instance()
        if app is not None:
            menu.setStyleSheet(app.styleSheet())

        enabled_action = menu.addAction(self.t("trim_enabled"))
        if enabled_action:
            enabled_action.setCheckable(True)
            enabled_action.setChecked(self.trim_manager.enabled)
            enabled_action.toggled.connect(self._set_trim_enabled)

        menu.addSeparator()

        max_menu = menu.addMenu(self.t("trim_max_lines"))
        if max_menu:
            for value in (1000, 5000, 20000):
                action = max_menu.addAction(str(value))
                if action:
                    action.setCheckable(True)
                    action.setChecked(self.trim_manager.max_lines == value)
                    action.triggered.connect(
                        lambda _=False, v=value: self._set_max_lines(v)
                    )

        batch_menu = menu.addMenu(self.t("trim_batch_lines"))
        if batch_menu:
            for value in (200, 800, 2000):
                action = batch_menu.addAction(str(value))
                if action:
                    action.setCheckable(True)
                    action.setChecked(self.trim_manager.batch_lines == value)
                    action.triggered.connect(
                        lambda _=False, v=value: self._set_batch_lines(v)
                    )

        self.trim_menu_button.setMenu(menu)

    def _set_trim_enabled(self, enabled: bool) -> None:
        self.trim_manager.enabled = enabled

    def _set_max_lines(self, value: int) -> None:
        self.trim_manager.max_lines = value
        self._rebuild_trim_menu()
        self.trim_manager.trim_if_needed(self.terminal_display.document())  # type: ignore[arg-type]

    def _set_batch_lines(self, value: int) -> None:
        self.trim_manager.batch_lines = value
        self._rebuild_trim_menu()

    # ── 终端模式 ─────────────────────────────────────────────

    def toggle_terminal_mode(self) -> None:
        """切换终端模式 / 普通模式。"""
        self.terminal_mode = not self.terminal_mode
        self.terminal_mode_button.setChecked(self.terminal_mode)

        self.terminal_display.setVisible(not self.terminal_mode)
        self.terminal_emulator.setVisible(self.terminal_mode)

        # 隐藏/显示发送区域和校验和区域
        for w in self._send_area_widgets + self._checksum_area_widgets:
            w.setVisible(not self.terminal_mode)

        # 终端模式下隐藏部分控制按钮
        self.clear_send_button.setVisible(not self.terminal_mode)
        self.receive_mode_button.setVisible(not self.terminal_mode)
        self.send_mode_button.setVisible(not self.terminal_mode)
        self.auto_scroll_checkbox.setVisible(not self.terminal_mode)
        self.timestamp_checkbox.setVisible(not self.terminal_mode)

        if self.terminal_mode:
            self.terminal_emulator.enable_ansi_colors = self.enable_ansi_colors
            self.terminal_emulator.setFocus()

        self.update_texts()

    def _on_terminal_key(self, data: bytes) -> None:
        """终端模拟器键盘输入 → 发送到串口。"""
        if self.serial_handler.is_open():
            self.serial_handler.write_data(data)

    # ── 搜索 ─────────────────────────────────────────────────

    def _open_search(self) -> None:
        self.search_bar.show_bar()

    def _close_search(self) -> None:
        self._clear_search_highlights()

    def _do_search(self, text: str, forward: bool, case_sensitive: bool) -> None:
        if self.terminal_mode:
            self._search_terminal(text, forward, case_sensitive)
        else:
            self._search_normal(text, forward, case_sensitive)

    def _search_normal(self, text: str, forward: bool, case_sensitive: bool) -> None:
        doc = self.terminal_display.document()
        cursor = self.terminal_display.textCursor()

        find_flags = QTextDocument.FindFlag(0)
        if not forward:
            find_flags |= QTextDocument.FindFlag.FindBackward
        if case_sensitive:
            find_flags |= QTextDocument.FindFlag.FindCaseSensitively

        result = doc.find(text, cursor, find_flags)

        if result.isNull():
            wrapped_cursor = QTextCursor(doc)
            if not forward:
                wrapped_cursor.movePosition(QTextCursor.MoveOperation.End)
            result = doc.find(text, wrapped_cursor, find_flags)

        if not result.isNull():
            self.terminal_display.setTextCursor(result)
            total = self._count_matches(doc, text, case_sensitive)
            current = self._current_match_index(doc, result, text, case_sensitive)
            self.search_bar.update_result(current, total)
        else:
            self.search_bar.set_no_result()

    def _search_terminal(self, text: str, forward: bool, case_sensitive: bool) -> None:
        grid = self.terminal_emulator.grid
        rows = len(grid)
        cols = self.terminal_emulator.cols

        if not text:
            self.search_bar.set_no_result()
            return

        matches: list[tuple[int, int]] = []
        for r in range(rows):
            row_text = "".join(cell.char for cell in grid[r])
            start = 0
            while True:
                if case_sensitive:
                    idx = row_text.find(text, start)
                else:
                    idx = row_text.lower().find(text.lower(), start)
                if idx == -1:
                    break
                matches.append((r, idx))
                start = idx + 1

        if not matches:
            self.search_bar.set_no_result()
            self.terminal_emulator.search_highlight = None
            self.terminal_emulator._dirty = True
            self.terminal_emulator._schedule_render()
            return

        cur_row = self.terminal_emulator.cursor_row
        cur_col = self.terminal_emulator.cursor_col

        if forward:
            target = None
            for r, c in matches:
                if (r, c) > (cur_row, cur_col):
                    target = (r, c)
                    break
            if target is None:
                target = matches[0]
        else:
            target = None
            for r, c in reversed(matches):
                if (r, c) < (cur_row, cur_col):
                    target = (r, c)
                    break
            if target is None:
                target = matches[-1]

        match_idx = matches.index(target) + 1
        self.search_bar.update_result(match_idx, len(matches))

        self.terminal_emulator.search_highlight = target
        self.terminal_emulator.cursor_row = target[0]
        self.terminal_emulator.cursor_col = target[1]
        self.terminal_emulator._dirty = True
        self.terminal_emulator._schedule_render()

    def _clear_search_highlights(self) -> None:
        if self.terminal_mode:
            self.terminal_emulator.search_highlight = None
            self.terminal_emulator._dirty = True
            self.terminal_emulator._schedule_render()

    @staticmethod
    def _count_matches(doc: QTextDocument, text: str, case_sensitive: bool) -> int:
        cursor = QTextCursor(doc)
        flags = QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        count = 0
        while True:
            cursor = doc.find(text, cursor, flags)
            if cursor.isNull():
                break
            count += 1
        return count

    @staticmethod
    def _current_match_index(
        doc: QTextDocument,
        current: QTextCursor,
        text: str,
        case_sensitive: bool,
    ) -> int:
        cursor = QTextCursor(doc)
        flags = QTextDocument.FindFlag(0)
        if case_sensitive:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        idx = 0
        while True:
            cursor = doc.find(text, cursor, flags)
            if cursor.isNull():
                break
            idx += 1
            if cursor.selectionStart() == current.selectionStart():
                return idx
        return 0

    # ── 串口操作 ─────────────────────────────────────────────

    def refresh_ports(self) -> None:
        self.port_combo.clear()
        for port in self.serial_handler.get_available_ports():
            self.port_combo.addItem(port)

    def toggle_connection(self) -> None:
        if self.serial_handler.is_open():
            self.manual_disconnect = True
            self.close_serial()
        else:
            self.open_serial()

    def open_serial(self) -> None:
        if self.serial_handler.is_open():
            return

        self.manual_disconnect = False
        port = self.port_combo.currentText()
        if not port:
            QMessageBox.warning(self, self.t("warning"), self.t("select_port"))
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
                self,
                self.t("error"),
                self.t("open_port_failed").format(self.serial_handler.last_error or ""),
            )
            return

        self.current_port = port
        self.serial_handler.set_dtr(self.dtr_checkbox.isChecked())
        self.serial_handler.set_rts(self.rts_checkbox.isChecked())

        if not self.terminal_mode:
            self.append_to_terminal(
                self.t("connected").format(port) + "\n", with_timestamp=True
            )

        self.update_texts()

    def close_serial(self, silent: bool = False, device_lost: bool = False) -> None:
        was_open = self.serial_handler.is_open()
        if was_open:
            self.serial_handler.close()

        if was_open and not silent and not self.terminal_mode:
            if device_lost:
                msg = self.t("device_disconnected").format(self.current_port) + "\n"
            else:
                msg = self.t("disconnected") + "\n"
            self.append_to_terminal(msg, with_timestamp=True)

        self.update_texts()

    def toggle_dtr(self) -> None:
        self.serial_handler.set_dtr(self.dtr_checkbox.isChecked())

    def toggle_rts(self) -> None:
        self.serial_handler.set_rts(self.rts_checkbox.isChecked())

    # ── 终端显示 ─────────────────────────────────────────────

    @staticmethod
    def get_timestamp() -> str:
        return datetime.now().strftime("[%H:%M:%S.%f")[:-3] + "] "

    def append_to_terminal(self, text: str, with_timestamp: bool = True) -> None:
        saved_cursor = self.terminal_display.textCursor()
        has_selection = saved_cursor.hasSelection()

        end_cursor = QTextCursor(self.terminal_display.document())
        end_cursor.movePosition(QTextCursor.MoveOperation.End)
        self.terminal_display.setTextCursor(end_cursor)

        cursor = self.terminal_display.textCursor()
        cursor.beginEditBlock()
        if with_timestamp and self.show_timestamp:
            cursor.insertText(
                self.get_timestamp(), self.ansi_parser.get_timestamp_format()
            )

        if not self.enable_ansi_colors:
            clean_text = self.ansi_parser.strip_ansi(text)
            cursor.insertText(clean_text)
        else:
            segments = self.ansi_parser.parse_text(text)
            for segment_text, fmt in segments:
                cursor.insertText(segment_text, fmt)

        cursor.endEditBlock()

        self.trim_manager.trim_if_needed(self.terminal_display.document())  # type: ignore[arg-type]

        if has_selection:
            self.terminal_display.setTextCursor(saved_cursor)
        elif self.auto_scroll:
            self.terminal_display.moveCursor(QTextCursor.MoveOperation.End)
        else:
            self.terminal_display.setTextCursor(saved_cursor)

    def _on_serial_data(self, data: bytes) -> None:
        if not data:
            return

        if self.terminal_mode:
            # 终端模式：直接交给模拟器处理
            self.terminal_emulator.process_bytes(data)
        elif self.receive_hex_mode:
            text = format_hex(data) + "\n"
            self.append_to_terminal(text, with_timestamp=True)
        else:
            text = data.decode("utf-8", errors="backslashreplace")
            if not text.endswith("\n"):
                text += "\n"
            self.append_to_terminal(text, with_timestamp=True)

    def _on_serial_error(self, message: str) -> None:
        if self.terminal_mode:
            err_text = self.t("read_error").format(message)
            self.terminal_emulator.process_bytes(
                err_text.encode("utf-8", errors="replace")
            )
        else:
            self.append_to_terminal(
                self.t("read_error").format(message) + "\n", with_timestamp=True
            )

    # ── 数据发送 ─────────────────────────────────────────────

    def send_data(self) -> None:
        if not self.serial_handler.is_open():
            QMessageBox.warning(self, self.t("warning"), self.t("not_connected"))
            return

        data = self.send_input.text()
        if not data:
            return

        auto_checksum = self.auto_checksum_checkbox.isChecked()
        checksum_start = self.checksum_start_spinbox.value()
        checksum_end_mode = self.checksum_end_combo.currentIndex()

        try:
            byte_values = parse_payload(data, is_hex=self.send_hex_mode)
        except ValueError:
            QMessageBox.warning(self, self.t("warning"), self.t("hex_even_chars"))
            return

        # 添加行尾符
        line_ending = self.line_ending_combo.currentData()
        if line_ending:
            byte_values += line_ending.encode("utf-8")

        display_data = data
        if auto_checksum:
            res = apply_checksum(
                byte_values,
                checksum_start_1based=checksum_start,
                checksum_end_mode=checksum_end_mode,
            )
            byte_values = res.payload
            if res.valid_range and res.checksum is not None:
                display_data += self.t("ck_tag").format(res.checksum)
            else:
                display_data += self.t("ck_invalid_range")

        try:
            if not self.serial_handler.write_data(byte_values):
                raise RuntimeError(self.serial_handler.last_error or "write failed")
            sent_key = "sent_hex" if self.send_hex_mode else "sent"
            self.append_to_terminal(
                self.t(sent_key).format(display_data) + "\n", with_timestamp=True
            )
            self.send_input.clear()
        except Exception as e:
            QMessageBox.critical(
                self, self.t("error"), self.t("send_failed").format(str(e))
            )

    # ── 模式切换 ─────────────────────────────────────────────

    def clear_receive_area(self) -> None:
        if self.terminal_mode:
            self.terminal_emulator.clear_screen()
        else:
            self.terminal_display.clear()

    def clear_send_area(self) -> None:
        self.send_input.clear()

    def toggle_receive_mode(self) -> None:
        self.receive_hex_mode = not self.receive_hex_mode
        self.receive_mode_button.setText(
            self.t("receive_mode_hex")
            if self.receive_hex_mode
            else self.t("receive_mode_asc")
        )

    def toggle_send_mode(self) -> None:
        self.send_hex_mode = not self.send_hex_mode
        self.send_mode_button.setText(
            self.t("send_mode_hex") if self.send_hex_mode else self.t("send_mode_asc")
        )
        self.send_input.setPlaceholderText(
            self.t("hex_placeholder")
            if self.send_hex_mode
            else self.t("ascii_placeholder")
        )
        self.update_texts()

    def toggle_auto_scroll(self) -> None:
        self.auto_scroll = self.auto_scroll_checkbox.isChecked()

    def toggle_timestamp(self) -> None:
        self.show_timestamp = self.timestamp_checkbox.isChecked()

    def toggle_ansi_colors(self) -> None:
        self.enable_ansi_colors = self.ansi_colors_checkbox.isChecked()
        self.terminal_emulator.enable_ansi_colors = self.enable_ansi_colors

    def toggle_auto_reconnect(self) -> None:
        self.auto_reconnect = self.auto_reconnect_checkbox.isChecked()

    # ── 设备检测 ─────────────────────────────────────────────

    def check_device_connection(self) -> None:
        available_ports = self.serial_handler.get_available_ports()

        if self.serial_handler.is_open() and self.current_port:
            if self.current_port not in available_ports:
                self.close_serial(silent=False, device_lost=True)

        if (
            self.auto_reconnect
            and not self.serial_handler.is_open()
            and not self.manual_disconnect
        ):
            if self.current_port and self.current_port in available_ports:
                if not self.terminal_mode:
                    self.append_to_terminal(
                        self.t("reconnecting").format(self.current_port) + "\n",
                        with_timestamp=True,
                    )
                idx = self.port_combo.findText(self.current_port)
                if idx >= 0:
                    self.port_combo.setCurrentIndex(idx)
                self.open_serial()
            elif available_ports:
                for port in available_ports:
                    if "ttyUSB" in port or "ttyACM" in port:
                        if not self.terminal_mode:
                            self.append_to_terminal(
                                self.t("device_found").format(port) + "\n",
                                with_timestamp=True,
                            )
                        self.refresh_ports()
                        idx = self.port_combo.findText(port)
                        if idx >= 0:
                            self.port_combo.setCurrentIndex(idx)
                        self.current_port = port
                        self.open_serial()
                        break

    # ── 校验和 ───────────────────────────────────────────────

    def calculate_checksum(self) -> None:
        data = self.send_input.text()
        if not data:
            self.checksum_input.clear()
            return

        try:
            byte_values = parse_payload(data, is_hex=self.send_hex_mode)
        except ValueError:
            self.checksum_input.setText(self.t("invalid_hex"))
            return

        auto_checksum = self.auto_checksum_checkbox.isChecked()
        checksum_start = self.checksum_start_spinbox.value()
        checksum_end_mode = self.checksum_end_combo.currentIndex()

        if auto_checksum:
            res = apply_checksum(
                byte_values,
                checksum_start_1based=checksum_start,
                checksum_end_mode=checksum_end_mode,
            )
            if res.valid_range and res.checksum is not None:
                self.checksum_input.setText(
                    f"{res.checksum:02X} (0x{res.checksum:02X})"
                )
            else:
                self.checksum_input.setText(self.t("ck_invalid_range"))
        else:
            checksum = sum(byte_values) & 0xFF
            self.checksum_input.setText(f"{checksum:02X} (0x{checksum:02X})")

    # ── 对话框 ───────────────────────────────────────────────

    def open_trimmed_logs_dir(self) -> None:
        try:
            self.trim_manager.log_dir.mkdir(parents=True, exist_ok=True)
            ok = QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.trim_manager.log_dir))
            )
            if not ok:
                raise RuntimeError(str(self.trim_manager.log_dir))
        except Exception as e:
            QMessageBox.critical(
                self, self.t("error"), self.t("open_trimmed_logs_failed").format(str(e))
            )

    def show_help(self) -> None:
        dialog = HelpDialog(self, language=self.language)
        dialog.exec()

    # ── 设置持久化 ───────────────────────────────────────────

    def load_settings(self) -> None:
        settings = ConfigManager.load_settings()

        if "geometry" in settings:
            self.restoreGeometry(bytes.fromhex(settings["geometry"]))

        self.language = settings.get("language", "zh")
        self.theme_combo.setCurrentIndex(settings.get("theme_index", 0))
        self.baudrate_combo.setCurrentText(settings.get("baudrate", "115200"))
        self.parity_combo.setCurrentText(settings.get("parity", "None"))
        self.databits_combo.setCurrentText(settings.get("databits", "8"))
        self.stopbits_combo.setCurrentText(settings.get("stopbits", "1"))

        self.receive_hex_mode = settings.get("receive_hex_mode", False)
        self.send_hex_mode = settings.get("send_hex_mode", False)
        self.auto_scroll = settings.get("auto_scroll", True)
        self.show_timestamp = settings.get("show_timestamp", True)
        self.enable_ansi_colors = settings.get("enable_ansi_colors", True)
        self.auto_reconnect = settings.get("auto_reconnect", False)

        self.auto_scroll_checkbox.setChecked(self.auto_scroll)
        self.timestamp_checkbox.setChecked(self.show_timestamp)
        self.ansi_colors_checkbox.setChecked(self.enable_ansi_colors)
        self.auto_reconnect_checkbox.setChecked(self.auto_reconnect)

        self.auto_checksum_checkbox.setChecked(settings.get("auto_checksum", False))
        self.checksum_start_spinbox.setValue(settings.get("checksum_start", 1))
        self.checksum_end_combo.setCurrentIndex(settings.get("checksum_end_mode", 0))

        self.dtr_checkbox.setChecked(settings.get("dtr_state", False))
        self.rts_checkbox.setChecked(settings.get("rts_state", False))

        self.trim_manager.load_from_dict(settings)
        self._rebuild_trim_menu()

        # 恢复终端模式
        if settings.get("terminal_mode", False):
            self.toggle_terminal_mode()

    def save_settings(self) -> None:
        settings: dict[str, Any] = {
            "geometry": self.saveGeometry().data().hex(),
            "language": self.language,
            "theme_index": self.theme_combo.currentIndex(),
            "baudrate": self.baudrate_combo.currentText(),
            "parity": self.parity_combo.currentText(),
            "databits": self.databits_combo.currentText(),
            "stopbits": self.stopbits_combo.currentText(),
            "receive_hex_mode": self.receive_hex_mode,
            "send_hex_mode": self.send_hex_mode,
            "auto_scroll": self.auto_scroll,
            "show_timestamp": self.show_timestamp,
            "enable_ansi_colors": self.enable_ansi_colors,
            "auto_reconnect": self.auto_reconnect,
            "auto_checksum": self.auto_checksum_checkbox.isChecked(),
            "checksum_start": self.checksum_start_spinbox.value(),
            "checksum_end_mode": self.checksum_end_combo.currentIndex(),
            "dtr_state": self.dtr_checkbox.isChecked(),
            "rts_state": self.rts_checkbox.isChecked(),
            "terminal_mode": self.terminal_mode,
        }
        settings.update(self.trim_manager.to_dict())
        ConfigManager.save_settings(settings)
        self.quick_send_manager.save_settings()

    def closeEvent(self, event: Any) -> None:
        self.save_settings()
        self.device_check_timer.stop()
        self.close_serial(silent=True)
        self.quick_send_manager.close()
        event.accept()
