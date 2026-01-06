"""
ANSI 转义序列解析器

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""
import re
from PyQt6.QtGui import QTextCharFormat, QColor, QFont


class AnsiParser:
    """ANSI 转义序列解析器，支持彩色日志显示"""
    
    def __init__(self):
        self.enabled = True
        self.setup()
    
    def setup(self):
        """初始化解析器"""
        # ANSI 转义序列正则表达式
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        self.ansi_color_pattern = re.compile(r'\x1B\[([0-9;]*)m')
        
        # ANSI 前景色映射表 (30-37, 90-97)
        self.fg_colors = {
            '30': QColor(0, 0, 0),         # 黑色
            '31': QColor(205, 49, 49),     # 红色
            '32': QColor(13, 188, 121),    # 绿色
            '33': QColor(229, 229, 16),    # 黄色
            '34': QColor(36, 114, 200),    # 蓝色
            '35': QColor(188, 63, 188),    # 品红
            '36': QColor(17, 168, 205),    # 青色
            '37': QColor(229, 229, 229),   # 白色
            # 亮色前景 (90-97)
            '90': QColor(102, 102, 102),   # 亮黑色(灰色)
            '91': QColor(241, 76, 76),     # 亮红色
            '92': QColor(35, 209, 139),    # 亮绿色
            '93': QColor(245, 245, 67),    # 亮黄色
            '94': QColor(59, 142, 234),    # 亮蓝色
            '95': QColor(214, 112, 214),   # 亮品红
            '96': QColor(41, 184, 219),    # 亮青色
            '97': QColor(255, 255, 255),   # 亮白色
        }
        
        # 背景色映射表 (40-47, 100-107)
        self.bg_colors = {
            '40': QColor(0, 0, 0),
            '41': QColor(205, 49, 49),
            '42': QColor(13, 188, 121),
            '43': QColor(229, 229, 16),
            '44': QColor(36, 114, 200),
            '45': QColor(188, 63, 188),
            '46': QColor(17, 168, 205),
            '47': QColor(229, 229, 229),
            '100': QColor(102, 102, 102),
            '101': QColor(241, 76, 76),
            '102': QColor(35, 209, 139),
            '103': QColor(245, 245, 67),
            '104': QColor(59, 142, 234),
            '105': QColor(214, 112, 214),
            '106': QColor(41, 184, 219),
            '107': QColor(255, 255, 255),
        }
        
        # 当前文本格式
        self.current_format = QTextCharFormat()
        self.reset_format()

        # 时间戳格式（复用对象，避免重复创建）
        self._timestamp_format = QTextCharFormat()
        self._timestamp_format.setForeground(QColor(150, 150, 150))
    
    def reset_format(self):
        """重置文本格式为默认"""
        self.current_format = QTextCharFormat()
        # 移除默认前景色和背景色设置，使其跟随主题
        # self.current_format.setForeground(QColor(200, 200, 200))
        # self.current_format.setBackground(QColor(0, 0, 0))
    
    def parse_code(self, code):
        """解析 ANSI 转义码并更新当前格式"""
        if not code or code == 'm':
            return
        
        code = code.rstrip('m')
        if not code:
            return
        
        codes = code.split(';')
        
        for c in codes:
            if not c:
                continue
                
            if c == '0':  # 重置所有属性
                self.reset_format()
            elif c == '1':  # 加粗
                self.current_format.setFontWeight(QFont.Weight.Bold)
            elif c == '4':  # 下划线
                self.current_format.setFontUnderline(True)
            elif c == '7':  # 反转颜色
                fg = self.current_format.foreground().color()
                bg = self.current_format.background().color()
                self.current_format.setForeground(bg)
                self.current_format.setBackground(fg)
            elif c == '22':  # 正常强度
                self.current_format.setFontWeight(QFont.Weight.Normal)
            elif c == '24':  # 取消下划线
                self.current_format.setFontUnderline(False)
            elif c in self.fg_colors:
                self.current_format.setForeground(self.fg_colors[c])
            elif c in self.bg_colors:
                self.current_format.setBackground(self.bg_colors[c])
    
    def strip_ansi(self, text):
        """移除文本中的 ANSI 转义序列"""
        return self.ansi_escape.sub('', text)
    
    def parse_text(self, text):
        """
        解析带 ANSI 颜色的文本
        
        Returns:
            list of (text, format) tuples
        """
        if not self.enabled:
            return [(self.strip_ansi(text), self.current_format)]
        
        result = []
        last_pos = 0
        
        for match in self.ansi_color_pattern.finditer(text):
            # 添加转义序列之前的文本
            if match.start() > last_pos:
                plain_text = text[last_pos:match.start()]
                result.append((plain_text, QTextCharFormat(self.current_format)))
            
            # 解析 ANSI 代码并更新格式
            self.parse_code(match.group(1) + 'm')
            last_pos = match.end()
        
        # 添加剩余文本
        if last_pos < len(text):
            plain_text = text[last_pos:]
            result.append((plain_text, QTextCharFormat(self.current_format)))
        
        return result
    
    def get_timestamp_format(self):
        """获取时间戳的文本格式"""
        return self._timestamp_format
