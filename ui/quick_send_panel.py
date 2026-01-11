"""
快捷发送面板模块

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QSpinBox,
    QLabel, QAbstractItemView, QMenu, QDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction

from ui.dialogs import QuickSendItemDialog
from utils.i18n import I18N


class QuickSendPanel(QWidget):
    """快捷发送面板 - 独立窗口"""
    
    # 信号: content, is_hex, auto_checksum, checksum_start, checksum_end_mode, line_ending
    send_requested = pyqtSignal(str, bool, bool, int, int, str)
    
    def __init__(self, parent=None, language='zh'):
        super().__init__(parent, Qt.WindowType.Window)  # Qt.WindowType.Window 使其成为独立窗口
        self.language = language
        self.quick_send_queue = []
        self.quick_send_timer = QTimer()
        self.quick_send_timer.timeout.connect(self._send_next_in_queue)
        
        self.init_ui()

    def t(self, key):
        return I18N.get(self.language, key)
    
    def init_ui(self):
        self.setWindowTitle(self.t('quick_send_panel'))
        self.setMinimumWidth(300)
        self.setMinimumHeight(400)
        
        # 主布局
        main_layout = QVBoxLayout(self)
        
        # 列表控件 - 支持拖拽排序
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.itemDoubleClicked.connect(self._edit_item)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        self.add_button = QPushButton(self.t('add_item'))
        self.add_button.clicked.connect(self._add_item)
        self.delete_button = QPushButton(self.t('delete_item'))
        self.delete_button.clicked.connect(self._delete_item)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.delete_button)
        
        # 发送单个选中项
        self.send_selected_button = QPushButton(self.t('send_selected'))
        self.send_selected_button.clicked.connect(self._send_selected)
        
        # 顺序发送区域
        sequence_layout = QHBoxLayout()
        self.interval_label = QLabel(self.t('interval'))
        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(10, 10000)
        self.interval_spinbox.setValue(500)
        self.interval_spinbox.setSingleStep(100)
        sequence_layout.addWidget(self.interval_label)
        sequence_layout.addWidget(self.interval_spinbox)
        
        send_sequence_layout = QHBoxLayout()
        self.send_checked_button = QPushButton(self.t('send_all_checked'))
        self.send_checked_button.clicked.connect(self._start_sequence_send)
        self.stop_button = QPushButton(self.t('stop_send'))
        self.stop_button.clicked.connect(self.stop_sequence_send)
        self.stop_button.setEnabled(False)
        send_sequence_layout.addWidget(self.send_checked_button)
        send_sequence_layout.addWidget(self.stop_button)
        
        # 组装布局
        main_layout.addWidget(self.list_widget)
        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.send_selected_button)
        main_layout.addLayout(sequence_layout)
        main_layout.addLayout(send_sequence_layout)
    
    def update_language(self, language):
        """更新语言"""
        self.language = language

        self.setWindowTitle(self.t('quick_send_panel'))
        self.add_button.setText(self.t('add_item'))
        self.delete_button.setText(self.t('delete_item'))
        self.send_selected_button.setText(self.t('send_selected'))
        self.send_checked_button.setText(self.t('send_all_checked'))
        self.stop_button.setText(self.t('stop_send'))
        self.interval_label.setText(self.t('interval'))
    
    def _add_item(self):
        """添加新的快捷发送项"""
        dialog = QuickSendItemDialog(self, language=self.language)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            content, is_hex, auto_checksum, checksum_start, checksum_end_mode, line_ending = dialog.get_data()
            self.add_item_to_list(content, is_hex, auto_checksum, checksum_start=checksum_start, checksum_end_mode=checksum_end_mode, line_ending=line_ending)
    
    def add_item_to_list(self, content, is_hex=False, auto_checksum=False, checked=True, 
                          checksum_start=1, checksum_end_mode=0, line_ending=''):
        """向列表添加一个快捷发送项"""
        item = QListWidgetItem()
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        
        item.setData(Qt.ItemDataRole.UserRole, {
            'content': content,
            'is_hex': is_hex,
            'auto_checksum': auto_checksum,
            'checksum_start': checksum_start,
            'checksum_end_mode': checksum_end_mode,
            'line_ending': line_ending
        })
        
        display_text = self._format_display(content, is_hex, auto_checksum, checksum_start, checksum_end_mode, line_ending)
        item.setText(display_text)
        
        self.list_widget.addItem(item)
    
    def _format_display(self, content, is_hex, auto_checksum, checksum_start=1, checksum_end_mode=0, line_ending=''):
        """格式化列表项的显示文本"""
        tags = []
        if is_hex:
            tags.append("HEX")
        if auto_checksum:
            # 显示校验范围信息
            end_str = (["末尾", "-1", "-2", "-3", "-4"] if self.language == 'zh' else ["End", "-1", "-2", "-3", "-4"])[
                checksum_end_mode
            ]
            tags.append(f"CK:{checksum_start}~{end_str}")
        if line_ending:
            # 显示行尾符
            if line_ending == '\n':
                tags.append("LF" if self.language == 'en' else "LF")
            elif line_ending == '\r\n':
                tags.append("CRLF" if self.language == 'en' else "CRLF")
            elif line_ending == '\r':
                tags.append("CR" if self.language == 'en' else "CR")
        
        tag_str = f"[{','.join(tags)}] " if tags else ""
        return f"{tag_str}{content}"
    
    def _delete_item(self):
        """删除选中的快捷发送项"""
        current_row = self.list_widget.currentRow()
        if current_row >= 0:
            self.list_widget.takeItem(current_row)
    
    def _edit_item(self, item):
        """编辑快捷发送项"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        
        dialog = QuickSendItemDialog(
            self, 
            language=self.language,
            content=data['content'],
            is_hex=data['is_hex'],
            auto_checksum=data['auto_checksum'],
            checksum_start=data.get('checksum_start', 1),
            checksum_end_mode=data.get('checksum_end_mode', 0),
            line_ending=data.get('line_ending', '')
        )
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            content, is_hex, auto_checksum, checksum_start, checksum_end_mode, line_ending = dialog.get_data()
            item.setData(Qt.ItemDataRole.UserRole, {
                'content': content,
                'is_hex': is_hex,
                'auto_checksum': auto_checksum,
                'checksum_start': checksum_start,
                'checksum_end_mode': checksum_end_mode,
                'line_ending': line_ending
            })
            item.setText(self._format_display(content, is_hex, auto_checksum, checksum_start, checksum_end_mode, line_ending))
    
    def _show_context_menu(self, pos):
        """显示右键菜单"""
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        
        menu = QMenu(self)
        
        edit_action = QAction(self.t('edit'), self)
        edit_action.triggered.connect(lambda: self._edit_item(item))
        
        delete_action = QAction(self.t('delete'), self)
        delete_action.triggered.connect(lambda: self.list_widget.takeItem(self.list_widget.row(item)))
        
        send_action = QAction(self.t('send'), self)
        send_action.triggered.connect(lambda: self._send_item(item))
        
        menu.addAction(send_action)
        menu.addAction(edit_action)
        menu.addSeparator()
        menu.addAction(delete_action)
        
        menu.exec(self.list_widget.mapToGlobal(pos))
    
    def _send_selected(self):
        """发送当前选中的快捷发送项"""
        current_item = self.list_widget.currentItem()
        if current_item:
            self._send_item(current_item)
    
    def _send_item(self, item):
        """发送单个快捷发送项"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.send_requested.emit(
                data['content'],
                data['is_hex'],
                data['auto_checksum'],
                data.get('checksum_start', 1),
                data.get('checksum_end_mode', 0),
                data.get('line_ending', '')
            )
    
    def _start_sequence_send(self):
        """开始顺序发送勾选的项目"""
        self.quick_send_queue = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self.quick_send_queue.append(item)
        
        if not self.quick_send_queue:
            QMessageBox.information(
                self, 
                self.t('info'),
                self.t('check_items_first')
            )
            return
        
        self.send_checked_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        
        self._send_next_in_queue()
        if self.quick_send_queue:
            self.quick_send_timer.start(self.interval_spinbox.value())
    
    def _send_next_in_queue(self):
        """发送队列中的下一项"""
        if not self.quick_send_queue:
            self.stop_sequence_send()
            return
        
        item = self.quick_send_queue.pop(0)
        self._send_item(item)
        self.list_widget.setCurrentItem(item)
        
        if not self.quick_send_queue:
            self.stop_sequence_send()
    
    def stop_sequence_send(self):
        """停止顺序发送"""
        self.quick_send_timer.stop()
        self.quick_send_queue = []
        self.send_checked_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def get_items(self):
        """获取所有快捷发送项的数据"""
        items = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data:
                # 添加选中状态
                data['checked'] = (item.checkState() == Qt.CheckState.Checked)
                items.append(data)
        return items

    def load_items(self, items):
        """加载快捷发送项"""
        self.list_widget.clear()
        for data in items:
            self.add_item_to_list(
                content=data.get('content', ''),
                is_hex=data.get('is_hex', False),
                auto_checksum=data.get('auto_checksum', False),
                checked=data.get('checked', True),
                checksum_start=data.get('checksum_start', 1),
                checksum_end_mode=data.get('checksum_end_mode', 0),
                line_ending=data.get('line_ending', '')
            )
