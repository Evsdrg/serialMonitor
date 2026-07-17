"""Connection configuration controls independent from connection state."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from utils.settings import Rfc2217Settings, SerialSettings, TcpSettings


class ConnectionPanel(QGroupBox):
    mode_requested = pyqtSignal()
    connect_requested = pyqtSignal()
    refresh_requested = pyqtSignal()
    dtr_changed = pyqtSignal(int)
    rts_changed = pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()
        self.set_mode("serial")

    def _build_ui(self) -> None:
        self.port_label = QLabel()
        self.port_combo = QComboBox()
        self.refresh_button = QPushButton()
        self.refresh_button.clicked.connect(self.refresh_requested)

        self.connection_mode_button = QPushButton()
        self.connection_mode_button.clicked.connect(self.mode_requested)

        self.socket_host_label = QLabel()
        self.socket_host_input = QLineEdit()
        self.socket_host_input.setPlaceholderText("192.168.1.100")
        self.socket_host_input.setFixedWidth(180)
        self.socket_port_label = QLabel()
        self.socket_port_input = QLineEdit()
        self.socket_port_input.setValidator(QIntValidator(1, 65535, self))
        self.socket_port_input.setPlaceholderText("9000")
        self.socket_port_input.setFixedWidth(80)

        self.rfc2217_timeout_label = QLabel()
        self.rfc2217_timeout_spinbox = QDoubleSpinBox()
        self.rfc2217_timeout_spinbox.setRange(0.1, 30.0)
        self.rfc2217_timeout_spinbox.setSingleStep(0.5)
        self.rfc2217_timeout_spinbox.setDecimals(1)
        self.rfc2217_timeout_spinbox.setValue(3.0)
        self.rfc2217_timeout_spinbox.setSuffix(" s")
        self.rfc2217_ignore_control_checkbox = QCheckBox()

        self.baudrate_label = QLabel()
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(
            [
                "9600",
                "19200",
                "38400",
                "57600",
                "115200",
                "230400",
                "460800",
                "921600",
            ]
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
        self.dtr_checkbox.stateChanged.connect(self.dtr_changed)
        self.rts_checkbox = QCheckBox("RTS")
        self.rts_checkbox.stateChanged.connect(self.rts_changed)
        self.connect_button = QPushButton()
        self.connect_button.clicked.connect(self.connect_requested)

        row1 = QHBoxLayout()
        row1.addStretch()
        for widget in (
            self.connection_mode_button,
            self.port_label,
            self.port_combo,
            self.refresh_button,
            self.socket_host_label,
            self.socket_host_input,
            self.socket_port_label,
            self.socket_port_input,
            self.dtr_checkbox,
            self.rts_checkbox,
            self.connect_button,
        ):
            row1.addWidget(widget)
        row1.addStretch()

        row2 = QHBoxLayout()
        row2.addStretch()
        for widget in (
            self.parity_label,
            self.parity_combo,
            self.databits_label,
            self.databits_combo,
            self.stopbits_label,
            self.stopbits_combo,
            self.baudrate_label,
            self.baudrate_combo,
            self.rfc2217_timeout_label,
            self.rfc2217_timeout_spinbox,
            self.rfc2217_ignore_control_checkbox,
        ):
            row2.addWidget(widget)
        row2.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(row1)
        layout.addLayout(row2)

        self.local_serial_widgets = [
            self.port_label,
            self.port_combo,
            self.refresh_button,
        ]
        self.serial_parameter_widgets = [
            self.baudrate_label,
            self.baudrate_combo,
            self.parity_label,
            self.parity_combo,
            self.databits_label,
            self.databits_combo,
            self.stopbits_label,
            self.stopbits_combo,
        ]
        self.control_line_widgets = [self.dtr_checkbox, self.rts_checkbox]
        self.socket_connection_widgets = [
            self.socket_host_label,
            self.socket_host_input,
            self.socket_port_label,
            self.socket_port_input,
        ]
        self.rfc2217_option_widgets = [
            self.rfc2217_timeout_label,
            self.rfc2217_timeout_spinbox,
            self.rfc2217_ignore_control_checkbox,
        ]

    def set_mode(self, mode: str) -> None:
        serial_mode = mode == "serial"
        rfc2217_mode = mode == "rfc2217"
        for widget in self.local_serial_widgets:
            widget.setVisible(serial_mode)
        for widget in self.serial_parameter_widgets + self.control_line_widgets:
            widget.setVisible(serial_mode or rfc2217_mode)
        for widget in self.socket_connection_widgets:
            widget.setVisible(not serial_mode)
        for widget in self.rfc2217_option_widgets:
            widget.setVisible(rfc2217_mode)

    def select_serial_port(self, port: str) -> None:
        if not port:
            return
        index = self.port_combo.findText(port)
        if index < 0:
            self.port_combo.addItem(port)
            index = self.port_combo.findText(port)
        self.port_combo.setCurrentIndex(index)

    def set_controls_enabled(
        self, enabled: bool, *, mode: str, is_connected: bool
    ) -> None:
        self.connection_mode_button.setEnabled(enabled)
        for widget in (
            self.local_serial_widgets
            + self.serial_parameter_widgets
            + self.socket_connection_widgets
            + self.rfc2217_option_widgets
        ):
            widget.setEnabled(enabled)
        control_lines_available = mode in ("serial", "rfc2217")
        for widget in self.control_line_widgets:
            widget.setEnabled(
                control_lines_available and (enabled or is_connected)
            )

    @staticmethod
    def _port_value(text: str) -> int | None:
        try:
            port = int(text)
        except ValueError:
            return None
        return port if 1 <= port <= 65535 else None

    def capture_settings(
        self, mode: str
    ) -> SerialSettings | TcpSettings | Rfc2217Settings:
        if mode == "serial":
            return SerialSettings(
                port=self.port_combo.currentText(),
                baudrate=self.baudrate_combo.currentText(),
                parity=self.parity_combo.currentText(),
                databits=self.databits_combo.currentText(),
                stopbits=self.stopbits_combo.currentText(),
                dtr=self.dtr_checkbox.isChecked(),
                rts=self.rts_checkbox.isChecked(),
            )
        if mode == "tcp":
            return TcpSettings(
                host=self.socket_host_input.text().strip(),
                port=self._port_value(self.socket_port_input.text().strip()),
            )
        return Rfc2217Settings(
            host=self.socket_host_input.text().strip(),
            port=self._port_value(self.socket_port_input.text().strip()),
            baudrate=self.baudrate_combo.currentText(),
            parity=self.parity_combo.currentText(),
            databits=self.databits_combo.currentText(),
            stopbits=self.stopbits_combo.currentText(),
            dtr=self.dtr_checkbox.isChecked(),
            rts=self.rts_checkbox.isChecked(),
            network_timeout=self.rfc2217_timeout_spinbox.value(),
            ignore_set_control=self.rfc2217_ignore_control_checkbox.isChecked(),
        )

    def apply_settings(
        self,
        mode: str,
        settings: SerialSettings | TcpSettings | Rfc2217Settings,
    ) -> None:
        if mode == "tcp":
            assert isinstance(settings, TcpSettings)
            self.socket_host_input.setText(settings.host)
            self.socket_port_input.setText(
                str(settings.port) if settings.port else ""
            )
            return

        if mode == "serial":
            assert isinstance(settings, SerialSettings)
            if settings.port:
                index = self.port_combo.findText(settings.port)
                if index < 0:
                    self.port_combo.addItem(settings.port)
                    index = self.port_combo.findText(settings.port)
                self.port_combo.setCurrentIndex(index)
        else:
            assert isinstance(settings, Rfc2217Settings)
            self.socket_host_input.setText(settings.host)
            self.socket_port_input.setText(
                str(settings.port) if settings.port else ""
            )
            self.rfc2217_timeout_spinbox.setValue(settings.network_timeout)
            self.rfc2217_ignore_control_checkbox.setChecked(
                settings.ignore_set_control
            )

        assert isinstance(settings, (SerialSettings, Rfc2217Settings))
        self.baudrate_combo.setCurrentText(settings.baudrate)
        self.parity_combo.setCurrentText(settings.parity)
        self.databits_combo.setCurrentText(settings.databits)
        self.stopbits_combo.setCurrentText(settings.stopbits)
        self.dtr_checkbox.setChecked(settings.dtr)
        self.rts_checkbox.setChecked(settings.rts)
