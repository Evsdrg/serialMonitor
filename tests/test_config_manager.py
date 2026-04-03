"""
测试 utils/config_manager.py
"""

import json
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from utils.config_manager import ConfigManager, _get_config_dir


class TestGetConfigDir:
    def test_development_mode(self):
        with patch.object(ConfigManager, "_CONFIG_DIR", None):
            config_dir = _get_config_dir()
            assert config_dir.name == "config"
            assert config_dir.parent.name == "serialMonitor"


class TestConfigManager:
    def test_load_settings_file_not_exists(self, tmp_path):
        with patch.object(ConfigManager, "_CONFIG_DIR", tmp_path):
            ConfigManager._SETTINGS_FILE = tmp_path / "settings.json"
            ConfigManager._QUICK_SEND_FILE = tmp_path / "quick_sends.json"
            result = ConfigManager.load_settings()
            assert result == {}

    def test_load_settings_success(self, tmp_path):
        settings = {"language": "en", "baudrate": 9600}
        settings_file = tmp_path / "settings.json"
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(settings, f)

        with patch.object(ConfigManager, "_CONFIG_DIR", tmp_path):
            ConfigManager._SETTINGS_FILE = settings_file
            ConfigManager._QUICK_SEND_FILE = tmp_path / "quick_sends.json"
            result = ConfigManager.load_settings()
            assert result == settings

    def test_load_settings_invalid_json(self, tmp_path):
        settings_file = tmp_path / "settings.json"
        with open(settings_file, "w", encoding="utf-8") as f:
            f.write("invalid json{")

        with patch.object(ConfigManager, "_CONFIG_DIR", tmp_path):
            ConfigManager._SETTINGS_FILE = settings_file
            ConfigManager._QUICK_SEND_FILE = tmp_path / "quick_sends.json"
            result = ConfigManager.load_settings()
            assert result == {}

    def test_save_settings(self, tmp_path):
        settings = {"language": "zh", "baudrate": 115200}

        with patch.object(ConfigManager, "_CONFIG_DIR", tmp_path):
            ConfigManager._SETTINGS_FILE = tmp_path / "settings.json"
            ConfigManager._QUICK_SEND_FILE = tmp_path / "quick_sends.json"
            ConfigManager.save_settings(settings)

            with open(ConfigManager._SETTINGS_FILE, "r", encoding="utf-8") as f:
                result = json.load(f)
            assert result == settings

    def test_save_settings_creates_dir(self, tmp_path):
        config_dir = tmp_path / "new_config"
        settings = {"test": "value"}

        with patch.object(ConfigManager, "_CONFIG_DIR", config_dir):
            ConfigManager._SETTINGS_FILE = config_dir / "settings.json"
            ConfigManager._QUICK_SEND_FILE = config_dir / "quick_sends.json"
            ConfigManager.save_settings(settings)

            assert config_dir.exists()
            assert ConfigManager._SETTINGS_FILE.exists()

    def test_load_quick_sends_file_not_exists(self, tmp_path):
        with patch.object(ConfigManager, "_CONFIG_DIR", tmp_path):
            ConfigManager._SETTINGS_FILE = tmp_path / "settings.json"
            ConfigManager._QUICK_SEND_FILE = tmp_path / "quick_sends.json"
            result = ConfigManager.load_quick_sends()
            assert result == []

    def test_load_quick_sends_success(self, tmp_path):
        items = [
            {"content": "test1", "is_hex": False},
            {"content": "AA BB", "is_hex": True},
        ]
        quick_send_file = tmp_path / "quick_sends.json"
        with open(quick_send_file, "w", encoding="utf-8") as f:
            json.dump(items, f)

        with patch.object(ConfigManager, "_CONFIG_DIR", tmp_path):
            ConfigManager._SETTINGS_FILE = tmp_path / "settings.json"
            ConfigManager._QUICK_SEND_FILE = quick_send_file
            result = ConfigManager.load_quick_sends()
            assert result == items

    def test_load_quick_sends_invalid_json(self, tmp_path):
        quick_send_file = tmp_path / "quick_sends.json"
        with open(quick_send_file, "w", encoding="utf-8") as f:
            f.write("not valid json")

        with patch.object(ConfigManager, "_CONFIG_DIR", tmp_path):
            ConfigManager._SETTINGS_FILE = tmp_path / "settings.json"
            ConfigManager._QUICK_SEND_FILE = quick_send_file
            result = ConfigManager.load_quick_sends()
            assert result == []

    def test_save_quick_sends(self, tmp_path):
        items = [
            {"content": "AT", "is_hex": False, "checked": True},
            {"content": "AA 55", "is_hex": True, "checked": False},
        ]

        with patch.object(ConfigManager, "_CONFIG_DIR", tmp_path):
            ConfigManager._SETTINGS_FILE = tmp_path / "settings.json"
            ConfigManager._QUICK_SEND_FILE = tmp_path / "quick_sends.json"
            ConfigManager.save_quick_sends(items)

            with open(ConfigManager._QUICK_SEND_FILE, "r", encoding="utf-8") as f:
                result = json.load(f)
            assert result == items

    def test_save_quick_sends_unicode(self, tmp_path):
        items = [{"content": "你好世界", "is_hex": False}]

        with patch.object(ConfigManager, "_CONFIG_DIR", tmp_path):
            ConfigManager._SETTINGS_FILE = tmp_path / "settings.json"
            ConfigManager._QUICK_SEND_FILE = tmp_path / "quick_sends.json"
            ConfigManager.save_quick_sends(items)

            with open(ConfigManager._QUICK_SEND_FILE, "r", encoding="utf-8") as f:
                result = json.load(f)
            assert result == items

    def test_ensure_config_dir(self, tmp_path):
        config_dir = tmp_path / "ensure_test"

        with patch.object(ConfigManager, "_CONFIG_DIR", config_dir):
            ConfigManager._SETTINGS_FILE = config_dir / "settings.json"
            ConfigManager._QUICK_SEND_FILE = config_dir / "quick_sends.json"
            ConfigManager.ensure_config_dir()
            assert config_dir.exists()

    def test_ensure_config_dir_already_exists(self, tmp_path):
        config_dir = tmp_path / "existing"
        config_dir.mkdir()

        with patch.object(ConfigManager, "_CONFIG_DIR", config_dir):
            ConfigManager._SETTINGS_FILE = config_dir / "settings.json"
            ConfigManager._QUICK_SEND_FILE = config_dir / "quick_sends.json"
            ConfigManager.ensure_config_dir()
            assert config_dir.exists()
