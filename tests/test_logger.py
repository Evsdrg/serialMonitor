"""
测试 utils/logger.py
"""

import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.logger import get_log_dir, get_logger, setup_logging


class TestGetLogDir:
    def test_development_returns_temp_dir(self):
        log_dir = get_log_dir()
        assert "SerialMonitorLogs" in log_dir.name
        assert log_dir.parent == Path(tempfile.gettempdir())

    @patch.object(sys, "frozen", True, create=True)
    @patch.object(sys, "_MEIPASS", "/tmp/meipass", create=True)
    def test_pyinstaller_returns_exec_dir(self):
        log_dir = get_log_dir()
        assert "SerialMonitorLogs" in log_dir.name


class TestSetupLogging:
    def test_returns_root_logger(self):
        logger = setup_logging()
        assert logger.name == "root"
        assert logger.level == logging.INFO

    def test_custom_level(self):
        logger = setup_logging(level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_handlers_added_once(self):
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        root.handlers = []

        try:
            logger = setup_logging()
            assert len(logger.handlers) >= 1

            second_logger = setup_logging()
            assert len(second_logger.handlers) == len(logger.handlers)
        finally:
            root.handlers = original_handlers


class TestGetLogger:
    def test_get_logger_returns_named_logger(self):
        logger = get_logger("test_module")
        assert logger.name == "test_module"
        assert isinstance(logger, logging.Logger)


class TestGetLogDirPlatform:
    @patch.object(sys, "platform", "win32")
    def test_windows_suffix(self):
        log_dir = get_log_dir()
        assert log_dir.name == "SerialMonitorLogs_win"

    @patch.object(sys, "platform", "linux")
    def test_linux_suffix(self):
        log_dir = get_log_dir()
        assert log_dir.name == "SerialMonitorLogs_linux"

    @patch.object(sys, "platform", "darwin")
    def test_other_suffix(self):
        log_dir = get_log_dir()
        assert log_dir.name == "SerialMonitorLogs_other"


class TestSetupLoggingMore:
    def test_setup_with_debug_env(self, monkeypatch):
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        root.handlers = []
        monkeypatch.setenv("DEBUG", "1")
        try:
            logger = setup_logging()
            # DEBUG 模式应添加 console handler
            has_stream = any(
                isinstance(h, logging.StreamHandler) for h in logger.handlers
            )
            assert has_stream is True
        finally:
            root.handlers = original_handlers
            root.setLevel(original_level)
            monkeypatch.delenv("DEBUG", raising=False)

    def test_setup_logging_returns_early_with_handlers(self):
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        # 模拟已有 handler
        existing = logging.NullHandler()
        root.handlers = [existing]
        try:
            logger = setup_logging()
            # 不应重复添加
            assert existing in logger.handlers
        finally:
            root.handlers = original_handlers

    def test_file_handler_oserror(self, tmp_path, monkeypatch):
        root = logging.getLogger()
        original_handlers = list(root.handlers)
        original_level = root.level
        root.handlers = []
        root.setLevel(logging.INFO)

        # 通过 patch RotatingFileHandler 让其抛 OSError
        from logging.handlers import RotatingFileHandler
        with patch.object(RotatingFileHandler, "__init__",
                          side_effect=OSError("disk full")):
            try:
                # 不应抛异常
                setup_logging()
            finally:
                root.handlers = original_handlers
                root.setLevel(original_level)
