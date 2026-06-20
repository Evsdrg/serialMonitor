"""
pytest 配置文件
"""

import os
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def _set_qt_platform():
    """确保在无头环境使用 offscreen Qt 平台。"""
    yield


@pytest.fixture
def qapp():
    """提供 QApplication 实例（pytest-qt 兼容）。"""
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ── Hypothesis 配置 ───────────────────────────────────────────
from hypothesis import HealthCheck, settings, Verbosity  # noqa: E402

_DEFAULT_SUPPRESS = [HealthCheck.function_scoped_fixture, HealthCheck.differing_executors]

settings.register_profile(
    "ci",
    max_examples=100,
    deadline=2000,
    verbosity=Verbosity.normal,
    suppress_health_check=_DEFAULT_SUPPRESS,
)
settings.register_profile(
    "dev",
    max_examples=50,
    deadline=1000,
    suppress_health_check=_DEFAULT_SUPPRESS,
)
settings.register_profile(
    "debug",
    max_examples=10,
    deadline=2000,
    verbosity=Verbosity.verbose,
    suppress_health_check=_DEFAULT_SUPPRESS,
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
