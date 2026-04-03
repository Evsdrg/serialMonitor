"""
配置管理模块

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_config_dir() -> Path:
    """获取配置文件目录。

    优先级：
    1. 打包后（PyInstaller）→ 可执行文件同目录下的 config/
    2. 开发环境 → 脚本同目录下的 config/
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # PyInstaller 打包后，配置放在可执行文件同目录
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "config"


class ConfigManager:
    """配置管理类，所有配置以 JSON 文件存储。"""

    _CONFIG_DIR: Path | None = None
    _SETTINGS_FILE: Path | None = None
    _QUICK_SEND_FILE: Path | None = None

    @classmethod
    def _get_paths(cls) -> tuple[Path, Path, Path]:
        """懒加载配置路径。"""
        if cls._CONFIG_DIR is None:
            cls._CONFIG_DIR = _get_config_dir()
            cls._SETTINGS_FILE = cls._CONFIG_DIR / "settings.json"
            cls._QUICK_SEND_FILE = cls._CONFIG_DIR / "quick_sends.json"
        return cls._CONFIG_DIR, cls._SETTINGS_FILE, cls._QUICK_SEND_FILE  # type: ignore[return-value]

    @classmethod
    def ensure_config_dir(cls) -> None:
        """确保配置目录存在。"""
        config_dir, _, _ = cls._get_paths()
        config_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load_settings(cls) -> dict[str, Any]:
        """加载应用设置。"""
        _, settings_file, _ = cls._get_paths()
        if not settings_file.exists():
            return {}
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load settings: %s", e)
            return {}

    @classmethod
    def save_settings(cls, settings: dict[str, Any]) -> None:
        """保存应用设置。"""
        cls.ensure_config_dir()
        _, settings_file, _ = cls._get_paths()
        try:
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except OSError as e:
            logger.error("Failed to save settings: %s", e)

    @classmethod
    def load_quick_sends(cls) -> list[dict[str, Any]]:
        """加载快捷发送列表。"""
        _, _, quick_send_file = cls._get_paths()
        if not quick_send_file.exists():
            return []
        try:
            with open(quick_send_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load quick sends: %s", e)
            return []

    @classmethod
    def save_quick_sends(cls, items: list[dict[str, Any]]) -> None:
        """保存快捷发送列表。"""
        cls.ensure_config_dir()
        _, _, quick_send_file = cls._get_paths()
        try:
            with open(quick_send_file, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=4, ensure_ascii=False)
        except OSError as e:
            logger.error("Failed to save quick sends: %s", e)
