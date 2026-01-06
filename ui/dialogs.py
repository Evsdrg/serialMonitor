"""
对话框模块

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QCheckBox, QDialogButtonBox, QSpinBox, QComboBox, QTextBrowser
)

from utils.i18n import I18N


class HelpDialog(QDialog):
    """使用说明对话框"""
    
    def __init__(self, parent=None, language='zh'):
        super().__init__(parent)
        self.language = language
        self.init_ui()
        
    def t(self, key):
        return I18N.get(self.language, key)
        
    def init_ui(self):
        self.setWindowTitle(self.t('help'))
        self.setMinimumSize(600, 500)
        
        layout = QVBoxLayout(self)
        
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        text_browser.setMarkdown(self.t('help_content'))
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(text_browser)
        layout.addWidget(button_box)


class QuickSendItemDialog(QDialog):
    """快捷发送项编辑对话框"""
    
    def __init__(self, parent=None, language='zh', content='', is_hex=False, 
                 auto_checksum=False, checksum_start=1, checksum_end_mode=0):
        super().__init__(parent)
        self.language = language
        self.init_ui(content, is_hex, auto_checksum, checksum_start, checksum_end_mode)

    def t(self, key):
        return I18N.get(self.language, key)
    
    def init_ui(self, content, is_hex, auto_checksum, checksum_start, checksum_end_mode):
        self.setWindowTitle(self.t('edit_item'))
        
        self.setMinimumWidth(450)
        
        layout = QVBoxLayout(self)
        
        # 内容输入
        content_layout = QHBoxLayout()
        content_label = QLabel(self.t('dialog_content'))
        self.content_input = QLineEdit()
        self.content_input.setText(content)
        self.content_input.setPlaceholderText(self.t('dialog_placeholder'))
        content_layout.addWidget(content_label)
        content_layout.addWidget(self.content_input)
        
        # 选项行1: HEX模式 和 校验和
        options_layout = QHBoxLayout()
        self.hex_checkbox = QCheckBox(self.t('dialog_hex_mode'))
        self.hex_checkbox.setChecked(is_hex)
        self.checksum_checkbox = QCheckBox(self.t('dialog_auto_checksum'))
        self.checksum_checkbox.setChecked(auto_checksum)
        options_layout.addWidget(self.hex_checkbox)
        options_layout.addWidget(self.checksum_checkbox)
        options_layout.addStretch()
        
        # 校验范围设置（始终显示）
        checksum_range_layout = QHBoxLayout()
        range_label = QLabel(self.t('checksum_range'))
        self.checksum_start_spinbox = QSpinBox()
        self.checksum_start_spinbox.setRange(1, 9999)
        self.checksum_start_spinbox.setValue(checksum_start)
        self.checksum_start_spinbox.setFixedWidth(60)
        
        to_label = QLabel(self.t('checksum_to'))
        
        self.checksum_end_combo = QComboBox()
        self.checksum_end_combo.addItems([
            self.t('ck_end_no_tail'),
            self.t('ck_end_minus_1'),
            self.t('ck_end_minus_2'),
            self.t('ck_end_minus_3'),
            self.t('ck_end_minus_4')
        ])
        self.checksum_end_combo.setCurrentIndex(checksum_end_mode)
        
        checksum_range_layout.addWidget(range_label)
        checksum_range_layout.addWidget(self.checksum_start_spinbox)
        checksum_range_layout.addWidget(to_label)
        checksum_range_layout.addWidget(self.checksum_end_combo)
        checksum_range_layout.addStretch()
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout.addLayout(content_layout)
        layout.addLayout(options_layout)
        layout.addLayout(checksum_range_layout)
        layout.addWidget(button_box)
    
    def get_data(self):
        """获取对话框数据"""
        return (
            self.content_input.text(),
            self.hex_checkbox.isChecked(),
            self.checksum_checkbox.isChecked(),
            self.checksum_start_spinbox.value(),
            self.checksum_end_combo.currentIndex()  # 0=末尾, 1=-1, 2=-2, 3=-3, 4=-4
        )
