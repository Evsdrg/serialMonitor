"""
配置管理模块

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from utils.settings import AppSettings

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
        cls._save_json(settings_file, settings, "settings")

    @classmethod
    def load_app_settings(cls) -> AppSettings:
        return AppSettings.from_dict(cls.load_settings())

    @classmethod
    def save_app_settings(cls, settings: AppSettings) -> None:
        cls.save_settings(settings.to_dict())

    @classmethod
    def load_quick_sends(cls) -> list[dict[str, Any]]:
        """加载快捷发送列表。"""
        _, _, quick_send_file = cls._get_paths()
        if not quick_send_file.exists():
            return []
        try:
            with open(quick_send_file, "r", encoding="utf-8") as f:
                raw_items = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load quick sends: %s", e)
            return []
        if not isinstance(raw_items, list):
            logger.warning("Ignoring malformed quick sends root")
            return []
        return [
            normalized
            for item in raw_items
            if (normalized := cls._normalize_quick_send(item)) is not None
        ]

    @staticmethod
    def _normalize_quick_send(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None

        checksum_start = item.get("checksum_start", 1)
        if isinstance(checksum_start, bool):
            checksum_start = 1
        try:
            checksum_start = int(checksum_start)
        except (OverflowError, TypeError, ValueError):
            checksum_start = 1
        if checksum_start < 1:
            checksum_start = 1

        checksum_end_mode = item.get("checksum_end_mode", 0)
        if isinstance(checksum_end_mode, bool):
            checksum_end_mode = 0
        try:
            checksum_end_mode = int(checksum_end_mode)
        except (OverflowError, TypeError, ValueError):
            checksum_end_mode = 0
        if not 0 <= checksum_end_mode <= 4:
            checksum_end_mode = 0

        line_ending = item.get("line_ending", "")
        if line_ending not in ("", "\n", "\r\n", "\r"):
            line_ending = ""

        normalized: dict[str, Any] = {}
        if "content" in item:
            normalized["content"] = (
                item.get("content") if isinstance(item.get("content"), str) else ""
            )
        if "is_hex" in item:
            normalized["is_hex"] = (
                item.get("is_hex") if isinstance(item.get("is_hex"), bool) else False
            )
        if "auto_checksum" in item:
            normalized["auto_checksum"] = (
                item.get("auto_checksum")
                if isinstance(item.get("auto_checksum"), bool)
                else False
            )
        if "checked" in item:
            normalized["checked"] = (
                item.get("checked") if isinstance(item.get("checked"), bool) else True
            )
        if "checksum_start" in item:
            normalized["checksum_start"] = checksum_start
        if "checksum_end_mode" in item:
            normalized["checksum_end_mode"] = checksum_end_mode
        if "line_ending" in item:
            normalized["line_ending"] = line_ending
        return normalized

    @classmethod
    def save_quick_sends(cls, items: list[dict[str, Any]]) -> None:
        """保存快捷发送列表。"""
        cls.ensure_config_dir()
        _, _, quick_send_file = cls._get_paths()
        cls._save_json(quick_send_file, items, "quick sends")

    @staticmethod
    def _save_json(path: Path, data: Any, label: str) -> None:
        temp_path: Path | None = None
        try:
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
            )
            os.close(fd)
            temp_path = Path(temp_name)
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
        except OSError as e:
            logger.error("Failed to save %s: %s", label, e)
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
