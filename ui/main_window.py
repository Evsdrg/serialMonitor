"""
主窗口模块

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

import codecs
import logging
import os
import sys
import tempfile
from dataclasses import replace
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
from core.connection_controller import (
    ConnectionController,
    ConnectionMode,
    Rfc2217ConnectionConfig,
    SerialConnectionConfig,
    TcpConnectionConfig,
)
from core.protocol import apply_checksum, format_hex, parse_payload
from core.payload_sender import PayloadRequest, PayloadSender, SendResult, SendStatus
from core.rfc2217_handler import Rfc2217Handler
from core.serial_handler import SerialHandler
from core.socket_handler import SocketHandler
from core.transport import (
    DisconnectReason,
    TransportError,
    TransportOperation,
    TransportState,
    TransportTransition,
)
from ui.quick_send_manager import QuickSendManager
from ui.connection_panel import ConnectionPanel
from ui.dialogs import HelpDialog
from ui.terminal_emulator import TerminalEmulator
from ui.search_bar import SearchBar
from utils.i18n import I18N
from utils.settings import (
    AppSettings,
    Rfc2217Settings,
    SerialSettings,
    TcpSettings,
)
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

        self._log_dir = self._prepare_log_dir()
        session = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_file = self._log_dir / f"trimmed_{session}_{os.getpid()}.log"

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    def _prepare_log_dir(self) -> Path:
        """准备裁剪日志目录：拒绝符号链接，失败则回退到私有临时目录。"""
        preferred = self._get_log_dir()
        try:
            preferred.mkdir(parents=True, exist_ok=True, mode=0o700)
            if preferred.is_dir() and not preferred.is_symlink():
                return preferred
            logger.warning("Trim log dir is not a regular directory: %s", preferred)
        except OSError as e:
            logger.warning("Failed to create trim log dir %s: %s", preferred, e)

        try:
            return Path(tempfile.mkdtemp(prefix="SerialMonitorTrimmedLogs_"))
        except OSError as e:
            logger.error("Failed to create fallback trim log dir: %s", e)
            return preferred

    def _get_log_dir(self) -> Path:
        base = Path(tempfile.gettempdir())
        if sys.platform.startswith("win"):
            suffix = "win"
        elif sys.platform.startswith("linux"):
            suffix = "linux"
        else:
            suffix = "other"
        return base / f"SerialMonitorTrimmedLogs_{suffix}"

    def _append_log(self, text: str) -> bool:
        if not text:
            return True
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(self._log_file, flags, 0o600)
        except OSError as e:
            logger.warning("Failed to open trim log: %s", e)
            return False
        try:
            with os.fdopen(fd, "a", encoding="utf-8", errors="replace") as f:
                f.write(text)
            return True
        except OSError as e:
            logger.warning("Failed to write trim log: %s", e)
            return False

    def trim_if_needed(self, document: QTextDocument) -> None:
        """检查并裁剪文档内容。"""
        if not self.enabled:
            return

        block_count = document.blockCount()
        if block_count <= self.max_lines:
            return

        excess = max(0, block_count - self.max_lines)
        trim_count = min(block_count - 1, max(self.batch_lines, excess))
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
        if not self._append_log(trimmed_text):
            return

        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        for _ in range(trim_count):
            if not cursor.movePosition(
                QTextCursor.MoveOperation.NextBlock, QTextCursor.MoveMode.KeepAnchor
            ):
                break
        cursor.removeSelectedText()

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
        self.socket_handler = SocketHandler()
        self.rfc2217_handler = Rfc2217Handler()
        self.connection_controller = ConnectionController(
            self.serial_handler,
            self.socket_handler,
            self.rfc2217_handler,
        )
        self.receive_hex_mode: bool = False
        self.send_hex_mode: bool = False
        self.auto_scroll: bool = True
        self.show_timestamp: bool = True
        self.auto_reconnect: bool = False
        self.current_port: Optional[str] = None
        self.current_socket_host: Optional[str] = None
        self.current_socket_port: Optional[int] = None
        self.current_rfc2217_host: Optional[str] = None
        self.current_rfc2217_port: Optional[int] = None
        self._serial_settings = SerialSettings()
        self._tcp_settings = TcpSettings()
        self._rfc2217_settings = Rfc2217Settings()
        self.language: str = "zh"
        self.enable_ansi_colors: bool = True
        self._receive_decoder = codecs.getincrementaldecoder("utf-8")(
            errors="backslashreplace"
        )
        self._receive_at_line_start: bool = True
        self._receive_pending_cr: bool = False
        self.quick_send_manager = QuickSendManager(self)
        self.terminal_mode: bool = False
        self._silent_disconnect_modes: set[str] = set()
        self._closing = False
        self.current_theme: str = "dark" if is_system_dark_mode() else "light"

        self.ansi_parser = AnsiParser()
        self.trim_manager = TerminalTrimManager()

        self.connection_controller.data_received.connect(self._on_serial_data)
        self.connection_controller.state_changed.connect(
            self._on_connection_state_changed
        )
        self.connection_controller.error_occurred.connect(
            self._on_connection_error
        )
        self.connection_controller.reconnecting.connect(self._on_reconnecting)
        self.payload_sender = PayloadSender(
            self.connection_controller.write_payload, self.is_connected
        )

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

        # ── 连接配置组 ──
        self.connection_panel = ConnectionPanel()
        self.port_group = self.connection_panel
        for name in (
            "port_label",
            "port_combo",
            "refresh_button",
            "connection_mode_button",
            "socket_host_label",
            "socket_host_input",
            "socket_port_label",
            "socket_port_input",
            "rfc2217_timeout_label",
            "rfc2217_timeout_spinbox",
            "rfc2217_ignore_control_checkbox",
            "baudrate_label",
            "baudrate_combo",
            "parity_label",
            "parity_combo",
            "databits_label",
            "databits_combo",
            "stopbits_label",
            "stopbits_combo",
            "dtr_checkbox",
            "rts_checkbox",
            "connect_button",
        ):
            setattr(self, name, getattr(self.connection_panel, name))
        self.connection_panel.mode_requested.connect(self.toggle_connection_mode)
        self.connection_panel.connect_requested.connect(self.toggle_connection)
        self.connection_panel.refresh_requested.connect(self.refresh_ports)
        self.connection_panel.dtr_changed.connect(self.toggle_dtr)
        self.connection_panel.rts_changed.connect(self.toggle_rts)
        self._update_connection_mode_ui()

        # ── 终端显示区域（普通模式） ──
        self.terminal_display = QTextEdit()
        self.terminal_display.setReadOnly(True)

        # ── 终端模拟器（终端模式） ──
        self.terminal_emulator = TerminalEmulator(rows=24, cols=80)
        self.terminal_emulator.hide()
        self.terminal_emulator.key_pressed.connect(self._on_terminal_key)
        self.terminal_emulator.paste_warning.connect(self._on_paste_warning)

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
        # 先建立条目，否则 load_settings() 在 update_texts() 之前恢复索引会失效
        self.checksum_end_combo.addItems(self._checksum_end_labels())
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

    def _checksum_end_labels(self) -> list[str]:
        """校验和结束位置下拉框的当前语言文本。"""
        if self.language == "zh":
            return [
                "末尾（无帧尾）",
                "-1（1字节帧尾）",
                "-2（2字节帧尾）",
                "-3（3字节帧尾）",
                "-4（4字节帧尾）",
            ]
        return [
            "End (no tail)",
            "-1 (1B tail)",
            "-2 (2B tail)",
            "-3 (3B tail)",
            "-4 (4B tail)",
        ]

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
        self.socket_host_label.setText(self.t("socket_host"))
        self.socket_port_label.setText(self.t("socket_port"))
        mode_text_keys = {
            "serial": "mode_serial",
            "tcp": "mode_tcp",
            "rfc2217": "mode_rfc2217",
        }
        self.connection_mode_button.setText(
            self.t(mode_text_keys[self.connection_mode])
        )
        self.baudrate_label.setText(self.t("baudrate"))
        self.parity_label.setText(self.t("parity"))
        self.databits_label.setText(self.t("databits"))
        self.stopbits_label.setText(self.t("stopbits"))
        self.rfc2217_timeout_label.setText(self.t("rfc2217_timeout"))
        self.rfc2217_ignore_control_checkbox.setText(
            self.t("rfc2217_ignore_control")
        )
        self.dtr_checkbox.setText(self.t("dtr"))
        self.rts_checkbox.setText(self.t("rts"))

        self.connect_button.setText(
            self.t("disconnect")
            if self.is_connection_active()
            else self.t("connect")
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

        # 原地改写条目文本，避免 clear() 丢失当前选择
        labels = self._checksum_end_labels()
        if self.checksum_end_combo.count() != len(labels):
            ck_idx = self.checksum_end_combo.currentIndex()
            self.checksum_end_combo.clear()
            self.checksum_end_combo.addItems(labels)
            if ck_idx >= 0:
                self.checksum_end_combo.setCurrentIndex(ck_idx)
        else:
            for index, text in enumerate(labels):
                self.checksum_end_combo.setItemText(index, text)

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

    # ── 连接模式 ─────────────────────────────────────────────

    @property
    def serial_handler(self) -> Any:
        return self._serial_handler

    @serial_handler.setter
    def serial_handler(self, handler: Any) -> None:
        self._serial_handler = handler
        controller = self.__dict__.get("connection_controller")
        if controller is not None:
            controller.replace_handler(ConnectionMode.SERIAL, handler)

    @property
    def socket_handler(self) -> Any:
        return self._socket_handler

    @socket_handler.setter
    def socket_handler(self, handler: Any) -> None:
        self._socket_handler = handler
        controller = self.__dict__.get("connection_controller")
        if controller is not None:
            controller.replace_handler(ConnectionMode.TCP, handler)

    @property
    def rfc2217_handler(self) -> Any:
        return self._rfc2217_handler

    @rfc2217_handler.setter
    def rfc2217_handler(self, handler: Any) -> None:
        self._rfc2217_handler = handler
        controller = self.__dict__.get("connection_controller")
        if controller is not None:
            controller.replace_handler(ConnectionMode.RFC2217, handler)

    @property
    def connection_mode(self) -> str:
        return self.connection_controller.mode.value

    @connection_mode.setter
    def connection_mode(self, mode: str) -> None:
        self.connection_controller.set_mode(mode)

    @property
    def active_handler(self) -> Any:
        return self.connection_controller.active_handler

    @property
    def manual_disconnect(self) -> bool:
        return self.connection_controller.manual_disconnect

    @manual_disconnect.setter
    def manual_disconnect(self, value: bool) -> None:
        self.connection_controller.manual_disconnect = value

    def is_connected(self) -> bool:
        return self.connection_controller.is_connected()

    def is_connection_active(self) -> bool:
        return self.connection_controller.is_active()

    def write_data(self, data: bytes) -> bool:
        return self.connection_controller.write_data(data)

    def connection_error(self) -> str:
        return self.connection_controller.connection_error()

    @property
    def _next_serial_reconnect_at(self) -> float:
        return self.connection_controller.reconnect_deadline(ConnectionMode.SERIAL)

    @property
    def _next_socket_reconnect_at(self) -> float:
        return self.connection_controller.reconnect_deadline(ConnectionMode.TCP)

    @property
    def _next_rfc2217_reconnect_at(self) -> float:
        return self.connection_controller.reconnect_deadline(ConnectionMode.RFC2217)

    def toggle_connection_mode(self) -> None:
        if self.is_connection_active():
            return
        self._capture_connection_settings(self.connection_mode)
        modes = ("serial", "tcp", "rfc2217")
        current_index = modes.index(self.connection_mode)
        self.connection_controller.set_mode(
            modes[(current_index + 1) % len(modes)]
        )
        self._apply_connection_settings(self.connection_mode)
        self._receive_decoder.reset()
        self._receive_at_line_start = True
        self._receive_pending_cr = False
        self._update_connection_mode_ui()
        self._set_connection_controls_enabled(True)
        self.update_texts()

    def _capture_connection_settings(self, mode: str) -> None:
        settings = self.connection_panel.capture_settings(mode)
        if isinstance(settings, SerialSettings):
            self._serial_settings = settings
        elif isinstance(settings, TcpSettings):
            self._tcp_settings = settings
        else:
            self._rfc2217_settings = settings

    def _apply_connection_settings(self, mode: str) -> None:
        if mode == ConnectionMode.SERIAL.value:
            settings = self._serial_settings
        elif mode == ConnectionMode.TCP.value:
            settings = self._tcp_settings
        else:
            settings = self._rfc2217_settings
        self.connection_panel.apply_settings(mode, settings)

    def _update_connection_mode_ui(self) -> None:
        self.connection_panel.set_mode(self.connection_mode)

    def _set_connection_controls_enabled(self, enabled: bool) -> None:
        self.connection_panel.set_controls_enabled(
            enabled,
            mode=self.connection_mode,
            is_connected=self.is_connected(),
        )

    def _on_connection_state_changed(
        self, mode: str, transition: TransportTransition
    ) -> None:
        if mode != self.connection_mode:
            return

        if (
            transition.current is TransportState.CONNECTED
            and not self.terminal_mode
        ):
            self.append_to_terminal(
                self.t("connected").format(transition.endpoint) + "\n",
                with_timestamp=True,
            )
        elif transition.current is TransportState.DISCONNECTED:
            silent = mode in self._silent_disconnect_modes
            self._silent_disconnect_modes.discard(mode)
            if (
                transition.session_was_connected
                and not silent
                and not self.terminal_mode
            ):
                if transition.reason is DisconnectReason.USER:
                    message = self.t("disconnected")
                elif mode == ConnectionMode.SERIAL.value:
                    message = self.t("device_disconnected").format(
                        transition.endpoint
                    )
                elif mode == ConnectionMode.TCP.value:
                    message = self.t("socket_disconnected").format(
                        transition.endpoint
                    )
                else:
                    message = self.t("rfc2217_disconnected").format(
                        transition.endpoint
                    )
                self.append_to_terminal(message + "\n", with_timestamp=True)

        self._set_connection_controls_enabled(
            transition.current is TransportState.DISCONNECTED
        )
        self.update_texts()

    def _on_reconnecting(self, mode: str, endpoint: str) -> None:
        if mode == ConnectionMode.SERIAL.value and endpoint:
            self.connection_panel.select_serial_port(endpoint)
            self._serial_settings = replace(self._serial_settings, port=endpoint)
            self.current_port = endpoint
        if mode == self.connection_mode and not self.terminal_mode:
            self.append_to_terminal(
                self.t("reconnecting").format(endpoint) + "\n",
                with_timestamp=True,
            )

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
            self.terminal_emulator.resize_to_fit()
            self.terminal_emulator.setFocus()

        self.update_texts()

    def _on_paste_warning(self, lines: int) -> None:
        """多行/超大粘贴请求二次确认时在状态栏提示。"""
        self.statusBar().showMessage(self.t("paste_confirm").format(lines), 3000)

    def _on_terminal_key(self, data: bytes) -> None:
        """终端模拟器键盘输入 → 发送到当前传输。"""
        self.send_payload(
            PayloadRequest(raw=data),
            display_sent=False,
            show_errors=False,
        )

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

        current = self.terminal_emulator.search_highlight
        current_pos = current[:2] if current is not None else None

        if forward:
            target = matches[0]
            if current_pos is not None:
                for match in matches:
                    if match > current_pos:
                        target = match
                        break
        else:
            target = matches[-1]
            if current_pos is not None:
                for match in reversed(matches):
                    if match < current_pos:
                        target = match
                        break

        match_idx = matches.index(target) + 1
        self.search_bar.update_result(match_idx, len(matches))

        self.terminal_emulator.search_highlight = (target[0], target[1], len(text))
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

    # ── 连接操作 ─────────────────────────────────────────────

    def refresh_ports(self) -> None:
        self.port_combo.clear()
        for port in self.serial_handler.get_available_ports():
            self.port_combo.addItem(port)

    def toggle_connection(self) -> None:
        if self.is_connection_active():
            self.manual_disconnect = True
            self.close_connection()
        else:
            self.open_connection()

    def open_connection(self, show_error: bool = True) -> None:
        if self.connection_mode == "rfc2217":
            self.open_rfc2217(show_error=show_error)
        elif self.connection_mode == "tcp":
            self.open_socket(show_error=show_error)
        else:
            self.open_serial(show_error=show_error)

    def close_connection(
        self, silent: bool = False, connection_lost: bool = False
    ) -> None:
        if self.connection_mode == "rfc2217":
            self.close_rfc2217(silent=silent)
        elif self.connection_mode == "tcp":
            self.close_socket(silent=silent, connection_lost=connection_lost)
        else:
            self.close_serial(silent=silent, device_lost=connection_lost)

    def open_serial(self, show_error: bool = True) -> None:
        if self.is_connection_active():
            return

        port = self.port_combo.currentText()
        if not port:
            QMessageBox.warning(self, self.t("warning"), self.t("select_port"))
            return
        self._capture_connection_settings(ConnectionMode.SERIAL.value)

        self._receive_decoder.reset()
        self._receive_at_line_start = True
        self._receive_pending_cr = False
        config = SerialConnectionConfig(
            port=port,
            baudrate=self.baudrate_combo.currentText(),
            parity=self.parity_combo.currentText(),
            databits=self.databits_combo.currentText(),
            stopbits=self.stopbits_combo.currentText(),
            dtr=self.dtr_checkbox.isChecked(),
            rts=self.rts_checkbox.isChecked(),
        )
        ok = self.connection_controller.connect(config, interactive=show_error)
        if not ok:
            return

        self.current_port = port
        self._set_connection_controls_enabled(False)
        self.update_texts()

    def open_socket(self, show_error: bool = True) -> None:
        if self.is_connection_active():
            return

        host = self.socket_host_input.text().strip()
        port_text = self.socket_port_input.text().strip()
        if not host or not port_text:
            if show_error:
                QMessageBox.warning(
                    self, self.t("warning"), self.t("enter_socket_endpoint")
                )
            return

        try:
            port = int(port_text)
        except ValueError:
            if show_error:
                QMessageBox.warning(
                    self, self.t("warning"), self.t("invalid_socket_port")
                )
            return
        if not 1 <= port <= 65535:
            if show_error:
                QMessageBox.warning(
                    self, self.t("warning"), self.t("invalid_socket_port")
                )
            return

        self._capture_connection_settings(ConnectionMode.TCP.value)
        self.current_socket_host = host
        self.current_socket_port = port
        self._receive_decoder.reset()
        self._receive_at_line_start = True
        self._receive_pending_cr = False

        ok = self.connection_controller.connect(
            TcpConnectionConfig(host, port), interactive=show_error
        )
        if not ok:
            return

        self._set_connection_controls_enabled(False)
        self.update_texts()

    def open_rfc2217(self, show_error: bool = True) -> None:
        if self.is_connection_active():
            return

        host = self.socket_host_input.text().strip()
        port_text = self.socket_port_input.text().strip()
        if not host or not port_text:
            if show_error:
                QMessageBox.warning(
                    self, self.t("warning"), self.t("enter_socket_endpoint")
                )
            return

        try:
            port = int(port_text)
        except ValueError:
            if show_error:
                QMessageBox.warning(
                    self, self.t("warning"), self.t("invalid_socket_port")
                )
            return
        if not 1 <= port <= 65535:
            if show_error:
                QMessageBox.warning(
                    self, self.t("warning"), self.t("invalid_socket_port")
                )
            return

        self._capture_connection_settings(ConnectionMode.RFC2217.value)
        self.current_rfc2217_host = host
        self.current_rfc2217_port = port
        self._receive_decoder.reset()
        self._receive_at_line_start = True
        self._receive_pending_cr = False

        config = Rfc2217ConnectionConfig(
            host=host,
            port=port,
            baudrate=self.baudrate_combo.currentText(),
            parity=self.parity_combo.currentText(),
            databits=self.databits_combo.currentText(),
            stopbits=self.stopbits_combo.currentText(),
            dtr=self.dtr_checkbox.isChecked(),
            rts=self.rts_checkbox.isChecked(),
            network_timeout=self.rfc2217_timeout_spinbox.value(),
            ignore_set_control=self.rfc2217_ignore_control_checkbox.isChecked(),
        )
        ok = self.connection_controller.connect(config, interactive=show_error)
        if not ok:
            return

        self._set_connection_controls_enabled(False)
        self.update_texts()

    def close_serial(self, silent: bool = False, device_lost: bool = False) -> None:
        if silent:
            self._silent_disconnect_modes.add(ConnectionMode.SERIAL.value)
        reason = (
            DisconnectReason.DEVICE_REMOVED
            if device_lost
            else DisconnectReason.USER
        )
        self.connection_controller.disconnect(reason)

    def close_socket(
        self, silent: bool = False, connection_lost: bool = False
    ) -> None:
        if not self.is_connection_active():
            return
        if silent:
            self._silent_disconnect_modes.add(ConnectionMode.TCP.value)
        reason = (
            DisconnectReason.REMOTE if connection_lost else DisconnectReason.USER
        )
        self.connection_controller.disconnect(reason)

    def close_rfc2217(self, silent: bool = False) -> None:
        if not self.is_connection_active():
            return
        if silent:
            self._silent_disconnect_modes.add(ConnectionMode.RFC2217.value)
        self.connection_controller.disconnect()

    def toggle_dtr(self) -> None:
        self.connection_controller.set_dtr(self.dtr_checkbox.isChecked())

    def toggle_rts(self) -> None:
        self.connection_controller.set_rts(self.rts_checkbox.isChecked())

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

    def _append_received_text(self, text: str) -> None:
        if self._receive_pending_cr:
            text = "\r" + text
            self._receive_pending_cr = False
        if text.endswith("\r"):
            text = text[:-1]
            self._receive_pending_cr = True

        for part in text.splitlines(keepends=True):
            self.append_to_terminal(
                part, with_timestamp=self._receive_at_line_start
            )
            self._receive_at_line_start = part.endswith(("\n", "\r"))

    def _on_serial_data(self, data: bytes) -> None:
        if not data:
            return

        if self.terminal_mode:
            # 终端模式：模拟器渲染，同时镜像到隐藏文档以保留历史/参与裁剪
            self.terminal_emulator.process_bytes(data)
            text = self._receive_decoder.decode(data, final=False)
            if text:
                self._append_received_text(text)
        elif self.receive_hex_mode:
            text = format_hex(data) + "\n"
            self.append_to_terminal(text, with_timestamp=True)
        else:
            text = self._receive_decoder.decode(data, final=False)
            if text:
                self._append_received_text(text)

    def _append_transport_error(self, message: str) -> None:
        if self.terminal_mode:
            self.terminal_emulator.process_bytes(
                (message + "\r\n").encode("utf-8", errors="replace")
            )
        # 错误插到数据流中间时，先冲刷数据流持有的行尾 CR，保持行序
        if self._receive_pending_cr:
            self._receive_pending_cr = False
            self.append_to_terminal(
                "\r", with_timestamp=self._receive_at_line_start
            )
        self.append_to_terminal(message + "\n", with_timestamp=True)
        # 错误消息以换行结尾，后续接收数据应从带时间戳的新行开始
        self._receive_at_line_start = True

    def _on_connection_error(
        self, mode: str, error: TransportError, interactive: bool
    ) -> None:
        if mode != self.connection_mode or error.reason is DisconnectReason.REMOTE:
            return

        if error.operation is TransportOperation.CONNECT:
            if mode == ConnectionMode.SERIAL.value:
                dialog_key = "open_port_failed"
                log_key = "open_port_failed"
            elif mode == ConnectionMode.TCP.value:
                dialog_key = "open_socket_failed"
                log_key = "socket_connect_error"
            else:
                dialog_key = "open_rfc2217_failed"
                log_key = "rfc2217_connect_error"
            if interactive:
                QMessageBox.critical(
                    self,
                    self.t("error"),
                    self.t(dialog_key).format(error.message),
                )
            elif mode == ConnectionMode.SERIAL.value:
                self._append_transport_error(self.t(log_key).format(error.message))
            else:
                self._append_transport_error(
                    self.t(log_key).format(error.endpoint, error.message)
                )
            return

        if mode == ConnectionMode.SERIAL.value:
            message = self.t("read_error").format(error.message)
        elif mode == ConnectionMode.TCP.value:
            message = self.t("socket_io_error").format(error.message)
        else:
            message = self.t("rfc2217_io_error").format(error.message)
        self._append_transport_error(message)

    # ── 数据发送 ─────────────────────────────────────────────

    def send_data(self) -> None:
        data = self.send_input.text()
        if not data:
            return
        line_ending = self.line_ending_combo.currentData()
        result = self.send_payload(
            PayloadRequest(
                text=data,
                is_hex=self.send_hex_mode,
                line_ending=(line_ending or "").encode("utf-8"),
                auto_checksum=self.auto_checksum_checkbox.isChecked(),
                checksum_start=self.checksum_start_spinbox.value(),
                checksum_end_mode=self.checksum_end_combo.currentIndex(),
            ),
            display_text=data,
            display_as_hex=self.send_hex_mode,
        )
        if result.accepted:
            self.send_input.clear()

    def send_payload(
        self,
        request: PayloadRequest,
        *,
        display_text: str | None = None,
        display_as_hex: bool = False,
        sent_key: str | None = None,
        queued_key: str | None = None,
        display_sent: bool = True,
        show_errors: bool = True,
    ) -> SendResult:
        result = self.payload_sender.send(request)
        if result.status is SendStatus.NOT_CONNECTED:
            if show_errors:
                QMessageBox.warning(
                    self, self.t("warning"), self.t("not_connected")
                )
            return result
        if result.status is SendStatus.INVALID_PAYLOAD:
            if show_errors:
                QMessageBox.warning(
                    self, self.t("warning"), self.t("hex_even_chars")
                )
            return result
        if result.status is SendStatus.INVALID_CHECKSUM_RANGE:
            if show_errors:
                QMessageBox.warning(
                    self, self.t("warning"), self.t("ck_invalid_range")
                )
            return result
        if result.status is SendStatus.WRITE_FAILED:
            if not show_errors:
                return result
            error = self.connection_error() or "write failed"
            QMessageBox.critical(
                self, self.t("error"), self.t("send_failed").format(error)
            )
            return result

        if display_sent and display_text is not None:
            if result.checksum is not None:
                display_text += self.t("ck_tag").format(result.checksum)
            if result.status is SendStatus.QUEUED:
                sent_key = queued_key or (
                    "queued_hex" if display_as_hex else "queued"
                )
            else:
                sent_key = sent_key or (
                    "sent_hex" if display_as_hex else "sent"
                )
            line = self.t(sent_key).format(display_text)
            if self.terminal_mode:
                self.statusBar().showMessage(line, 3000)
            else:
                self.append_to_terminal(line + "\n", with_timestamp=True)
        return result

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
        self._receive_decoder.reset()
        self._receive_at_line_start = True
        self._receive_pending_cr = False
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
        if self._closing:
            return
        if self.connection_mode == ConnectionMode.SERIAL.value:
            config = self.connection_controller.current_config()
            if isinstance(config, SerialConnectionConfig) and self.is_connected():
                if config.port not in self.serial_handler.get_available_ports():
                    self.connection_controller.disconnect(
                        DisconnectReason.DEVICE_REMOVED
                    )
        self.connection_controller.poll_reconnect(
            auto_reconnect=self.auto_reconnect
        )

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
        settings = ConfigManager.load_app_settings()

        if settings.geometry:
            self.restoreGeometry(bytes.fromhex(settings.geometry))

        self.language = settings.language
        self.theme_combo.setCurrentIndex(settings.theme_index)
        self._serial_settings = settings.serial
        self._tcp_settings = settings.tcp
        self._rfc2217_settings = settings.rfc2217
        self.connection_mode = settings.connection_mode
        self._apply_connection_settings(self.connection_mode)
        self._update_connection_mode_ui()

        self.receive_hex_mode = settings.receive_hex_mode
        self.send_hex_mode = settings.send_hex_mode
        self.auto_scroll = settings.auto_scroll
        self.show_timestamp = settings.show_timestamp
        self.enable_ansi_colors = settings.enable_ansi_colors
        self.auto_reconnect = settings.auto_reconnect

        self.auto_scroll_checkbox.setChecked(self.auto_scroll)
        self.timestamp_checkbox.setChecked(self.show_timestamp)
        self.ansi_colors_checkbox.setChecked(self.enable_ansi_colors)
        self.auto_reconnect_checkbox.setChecked(self.auto_reconnect)

        self.auto_checksum_checkbox.setChecked(settings.auto_checksum)
        self.checksum_start_spinbox.setValue(settings.checksum_start)
        self.checksum_end_combo.setCurrentIndex(settings.checksum_end_mode)

        self.trim_manager.enabled = settings.trim_enabled
        self.trim_manager.max_lines = settings.max_terminal_lines
        self.trim_manager.batch_lines = settings.trim_batch_lines
        self._rebuild_trim_menu()

        if settings.terminal_mode:
            self.toggle_terminal_mode()

    def save_settings(self) -> None:
        self._capture_connection_settings(self.connection_mode)
        settings = AppSettings(
            geometry=self.saveGeometry().data().hex(),
            language=self.language,
            theme_index=self.theme_combo.currentIndex(),
            connection_mode=self.connection_mode,
            serial=self._serial_settings,
            tcp=self._tcp_settings,
            rfc2217=self._rfc2217_settings,
            receive_hex_mode=self.receive_hex_mode,
            send_hex_mode=self.send_hex_mode,
            auto_scroll=self.auto_scroll,
            show_timestamp=self.show_timestamp,
            enable_ansi_colors=self.enable_ansi_colors,
            auto_reconnect=self.auto_reconnect,
            auto_checksum=self.auto_checksum_checkbox.isChecked(),
            checksum_start=self.checksum_start_spinbox.value(),
            checksum_end_mode=self.checksum_end_combo.currentIndex(),
            terminal_mode=self.terminal_mode,
            trim_enabled=self.trim_manager.enabled,
            max_terminal_lines=self.trim_manager.max_lines,
            trim_batch_lines=self.trim_manager.batch_lines,
        )
        ConfigManager.save_app_settings(settings)
        self.quick_send_manager.save_settings()

    def closeEvent(self, event: Any) -> None:
        self.save_settings()
        self._closing = True
        self._silent_disconnect_modes.update(
            mode.value for mode in ConnectionMode
        )
        self.close_connection(silent=True)
        # 关闭不可被传输层否决：无法停止的后台任务只记录，不阻止用户退出
        if not self.rfc2217_handler.shutdown(timeout_ms=3000):
            logger.warning("RFC2217 worker did not stop before close")
        if not self.serial_handler.shutdown(timeout_ms=1500):
            logger.warning("Serial reader did not stop before close")
        self.device_check_timer.stop()
        self.socket_handler.shutdown(timeout_ms=1000)
        self.quick_send_manager.close()
        self._closing = False
        event.accept()
