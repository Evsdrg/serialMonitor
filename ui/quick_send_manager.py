"""
Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from ui.quick_send_panel import QuickSendPanel
from utils.config_manager import ConfigManager
from core.protocol import parse_payload, apply_checksum


class QuickSendManager:
    """快捷发送面板管理器"""
    
    def __init__(self, main_window):
        self.main_window = main_window
        self.panel = None

    def toggle_panel(self):
        """切换快捷发送面板显示"""
        if self.panel is None:
            self.create_panel()
        
        if self.panel.isVisible():
            self.panel.hide()
        else:
            self.panel.show()
            # 使用 QTimer 延迟定位，等待窗口完全显示后再移动
            QTimer.singleShot(50, self._position_panel)

    def create_panel(self):
        """创建快捷发送面板"""
        self.panel = QuickSendPanel(None, language=self.main_window.language)
        self.panel.send_requested.connect(self.send_item)
        # 设置初始尺寸
        self.panel.resize(300, 450)
        
        # 加载保存的条目
        items = ConfigManager.load_quick_sends()
        if items:
            self.panel.load_items(items)

    def _position_panel(self):
        """将快捷发送面板定位到主窗口右侧"""
        if not self.panel or not self.panel.isVisible():
            return
        
        # 获取主窗口的屏幕位置
        main_geo = self.main_window.frameGeometry()
        # 计算面板位置：主窗口右边缘 + 间隙
        panel_x = main_geo.right() + 10
        panel_y = main_geo.top()
        
        # 如果 Wayland 返回的是 (0,0)，尝试使用屏幕信息作为备用
        if main_geo.x() == 0 and main_geo.y() == 0:
            # Wayland 下无法获取绝对位置，尝试获取屏幕尺寸并放在右侧合理位置
            screen = self.main_window.screen()
            if screen:
                screen_geo = screen.availableGeometry()
                # 假设主窗口在屏幕中央，将面板放到屏幕右侧 2/3 处
                panel_x = screen_geo.width() * 2 // 3
                panel_y = screen_geo.height() // 4
        
        self.panel.move(panel_x, panel_y)

    def send_item(self, content, is_hex, auto_checksum, checksum_start=1, checksum_end_mode=0, line_ending=''):
        """处理快捷发送请求"""
        if not self.main_window.serial_handler.is_open():
            QMessageBox.warning(self.main_window, self.main_window.t('warning'), self.main_window.t('not_connected'))
            return
        
        try:
            byte_values = parse_payload(content, is_hex=is_hex)

            # 添加行尾符
            if line_ending:
                byte_values += line_ending.encode('utf-8')

            content_display = content
            if auto_checksum:
                res = apply_checksum(
                    byte_values,
                    checksum_start_1based=checksum_start,
                    checksum_end_mode=checksum_end_mode,
                )
                byte_values = res.payload
                if res.valid_range and res.checksum is not None:
                    content_display += self.main_window.t('ck_tag').format(res.checksum)
                else:
                    content_display += self.main_window.t('ck_invalid_range')

            if not self.main_window.serial_handler.write_data(byte_values):
                raise RuntimeError(self.main_window.serial_handler.last_error or 'write failed')

            msg_key = 'quick_send_hex' if is_hex else 'quick_send_ascii'
            self.main_window.append_to_terminal(self.main_window.t(msg_key).format(content_display) + '\n', with_timestamp=True)
        except Exception as e:
            self.main_window.append_to_terminal(self.main_window.t('send_error').format(str(e)) + '\n', with_timestamp=True)

    def update_language(self, language):
        """更新语言"""
        if self.panel:
            self.panel.update_language(language)

    def close(self):
        """关闭面板"""
        if self.panel:
            self.panel.close()

    def save_settings(self):
        """保存快捷发送列表"""
        if self.panel:
            items = self.panel.get_items()
            ConfigManager.save_quick_sends(items)
