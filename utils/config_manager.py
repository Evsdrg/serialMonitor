"""
Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""
import json
import os
from pathlib import Path

class ConfigManager:
    """配置管理类"""
    
    # 配置文件目录 (当前目录下的 config 文件夹)
    CONFIG_DIR = Path("config")
    SETTINGS_FILE = CONFIG_DIR / "settings.json"
    QUICK_SEND_FILE = CONFIG_DIR / "quick_sends.json"

    @classmethod
    def ensure_config_dir(cls):
        """确保配置目录存在"""
        if not cls.CONFIG_DIR.exists():
            cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load_settings(cls):
        """加载应用设置"""
        if not cls.SETTINGS_FILE.exists():
            return {}
        try:
            with open(cls.SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    @classmethod
    def save_settings(cls, settings):
        """保存应用设置"""
        cls.ensure_config_dir()
        try:
            with open(cls.SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    @classmethod
    def load_quick_sends(cls):
        """加载快捷发送列表"""
        if not cls.QUICK_SEND_FILE.exists():
            return []
        try:
            with open(cls.QUICK_SEND_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    @classmethod
    def save_quick_sends(cls, items):
        """保存快捷发送列表"""
        cls.ensure_config_dir()
        try:
            with open(cls.QUICK_SEND_FILE, 'w', encoding='utf-8') as f:
                json.dump(items, f, indent=4, ensure_ascii=False)
        except Exception:
            pass
