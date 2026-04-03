"""
日志配置模块

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def get_log_dir() -> Path:
    """获取日志文件目录"""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys.executable).parent
    else:
        base = Path(tempfile.gettempdir())

    if sys.platform.startswith("win"):
        suffix = "SerialMonitorLogs_win"
    elif sys.platform.startswith("linux"):
        suffix = "SerialMonitorLogs_linux"
    else:
        suffix = "SerialMonitorLogs_other"

    return base / suffix


def setup_logging(
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    """配置日志系统

    Args:
        level: 日志级别
        max_bytes: 单个日志文件最大字节数
        backup_count: 保留的备份文件数

    Returns:
        配置好的根日志器
    """
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    session = datetime.now().strftime("%Y%m%d")
    log_file = log_dir / f"serialmonitor_{session}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if root_logger.handlers:
        return root_logger

    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_formatter = logging.Formatter("%(levelname)s: %(name)s - %(message)s")

    try:
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)
    except OSError as e:
        root_logger.warning("Failed to setup file logging: %s", e)

    if os.environ.get("DEBUG"):
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    root_logger.info("Logging initialized. Log file: %s", log_file)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器

    Args:
        name: 日志器名称

    Returns:
        日志器实例
    """
    return logging.getLogger(name)
