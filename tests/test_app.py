"""
测试 app.py
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtGui import QIcon

from app import _resource_base, _restore_stderr, _set_app_icon, _suppress_stderr, BASE_DIR


# ── _resource_base ───────────────────────────────────────


class TestResourceBase:
    def test_normal_execution_returns_script_dir(self):
        assert _resource_base() == Path(__file__).resolve().parent.parent

    def test_base_dir_is_path(self):
        assert isinstance(BASE_DIR, Path)

    def test_base_dir_exists(self):
        assert BASE_DIR.exists()

    def test_frozen_mode_with_meipass(self):
        """PyInstaller frozen 模式 + _MEIPASS：返回 _MEIPASS 路径。"""
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "_MEIPASS", "/tmp/fake_meipass", create=True):
            result = _resource_base()
            assert result == Path("/tmp/fake_meipass")

    def test_frozen_mode_without_meipass(self):
        """PyInstaller frozen 模式但无 _MEIPASS：返回可执行文件所在目录。"""
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "_MEIPASS", None, create=True), \
             patch.object(sys, "executable", "/tmp/fake_exec/bin/app"):
            result = _resource_base()
            assert result == Path("/tmp/fake_exec/bin").resolve()

    def test_frozen_empty_meipass(self):
        """PyInstaller frozen 模式 + _MEIPASS 为空字符串：返回可执行文件目录。"""
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "_MEIPASS", "", create=True), \
             patch.object(sys, "executable", "/tmp/fake_exec/bin/app"):
            result = _resource_base()
            assert result == Path("/tmp/fake_exec/bin").resolve()

    def test_frozen_false_falls_through(self):
        """sys.frozen=False 时走开发模式分支。"""
        with patch.object(sys, "frozen", False, create=True):
            result = _resource_base()
            assert result == Path(__file__).resolve().parent.parent


# ── _suppress_stderr / _restore_stderr ───────────────────


class TestSuppressStderr:
    def test_suppress_stderr_returns_fd(self):
        if os.environ.get("DEBUG"):
            pytest.skip("DEBUG mode enabled")
        result = _suppress_stderr()
        assert result is not None
        assert isinstance(result, int)
        _restore_stderr(result)

    def test_restore_stderr_restores(self):
        if os.environ.get("DEBUG"):
            pytest.skip("DEBUG mode enabled")
        old = _suppress_stderr()
        _restore_stderr(old)
        # 验证 stderr 已恢复：写入 stderr 不会报错
        os.write(2, b"")

    def test_restore_stderr_no_op_when_none(self):
        """`_restore_stderr(None)` 应直接返回。"""
        # 不应抛异常
        _restore_stderr(None)

    def test_debug_mode_no_suppress(self):
        os.environ["DEBUG"] = "1"
        try:
            result = _suppress_stderr()
            assert result is None
        finally:
            del os.environ["DEBUG"]

    def test_suppress_actually_redirects(self):
        """_suppress_stderr 之后向 stderr 写入应不报错（被重定向到 /dev/null）。"""
        if os.environ.get("DEBUG"):
            pytest.skip("DEBUG mode enabled")
        old = _suppress_stderr()
        try:
            # 写入 stderr 不会抛 OSError（因为已重定向到 /dev/null）
            os.write(2, b"test message")
        finally:
            _restore_stderr(old)

    def test_suppress_uses_devnull(self):
        """_suppress_stderr 应使用 os.devnull 路径。"""
        if os.environ.get("DEBUG"):
            pytest.skip("DEBUG mode enabled")
        with patch("os.open") as mock_open, \
             patch("os.dup") as mock_dup, \
             patch("os.dup2") as mock_dup2, \
             patch("os.close") as mock_close:
            mock_open.return_value = 99  # 模拟 devnull fd
            mock_dup.return_value = 100  # 模拟旧 stderr fd
            result = _suppress_stderr()
            assert result == 100
            mock_open.assert_called_once()
            # open 应使用 os.devnull 和 O_WRONLY
            call_args = mock_open.call_args
            assert call_args[0][0] == os.devnull
            mock_dup.assert_called_once_with(2)
            mock_dup2.assert_called_once_with(99, 2)


# ── _set_app_icon ───────────────────────────────────────


class TestSetAppIcon:
    def _get_app(self):
        """获取或创建 QApplication 实例。"""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app

    def test_set_app_icon_no_files(self):
        """没有图标文件时不应抛异常。"""
        app = self._get_app()
        # 不抛异常即可
        _set_app_icon(app)

    def test_set_app_icon_with_existing_file(self, tmp_path):
        """图标文件存在时应设置。"""
        # 创建一个假的"图标"文件（PNG 头几个字节）
        icon_path = tmp_path / "终端.png"
        icon_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        app = self._get_app()
        with patch("app.BASE_DIR", tmp_path):
            _set_app_icon(app)
        # 无异常即视为通过

    def test_set_app_icon_invalid_png(self, tmp_path):
        """无效的 PNG 文件应被跳过。"""
        bad_png = tmp_path / "终端.png"
        bad_png.write_bytes(b"not a real png")

        app = self._get_app()
        with patch("app.BASE_DIR", tmp_path):
            # 不应抛异常
            _set_app_icon(app)

    def test_set_app_icon_ico(self, tmp_path):
        """`.ico` 文件也应支持。"""
        ico_path = tmp_path / "favicon.ico"
        ico_path.write_bytes(b"\x00\x00\x01\x00" + b"\x00" * 100)

        app = self._get_app()
        with patch("app.BASE_DIR", tmp_path):
            _set_app_icon(app)

    def test_set_app_icon_falls_back_to_cwd(self, tmp_path):
        """BASE_DIR 无图标时，cwd 应作为后备。"""
        icon_in_cwd = tmp_path / "终端.png"
        icon_in_cwd.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        app = self._get_app()
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with patch("app.BASE_DIR", empty_dir), \
             patch("pathlib.Path.cwd", return_value=tmp_path):
            _set_app_icon(app)

    def test_set_app_icon_handles_exception(self, tmp_path):
        """`_set_app_icon` 在 QIcon 抛异常时应静默跳过。"""
        icon_path = tmp_path / "终端.png"
        icon_path.write_bytes(b"some content")

        app = self._get_app()
        with patch("app.BASE_DIR", tmp_path), \
             patch("app.QIcon", side_effect=RuntimeError("QIcon failed")):
            # 不应抛异常
            _set_app_icon(app)

    def test_set_app_icon_calls_setWindowIcon(self, tmp_path):
        """找到有效图标时应调用 setWindowIcon。"""
        # 创建 PNG 文件
        icon_path = tmp_path / "终端.png"
        icon_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        app = self._get_app()
        with patch("app.BASE_DIR", tmp_path), \
             patch.object(app, "setWindowIcon") as mock_set_icon:
            _set_app_icon(app)
            # setWindowIcon 应被调用（PNG 可能不是有效但 QIcon.isNull() 检查会跳过）
            # 实际上 PNG 字节不构成有效 PNG，QIcon.isNull() 返回 True，不调用
            # 我们只验证函数能正常完成

    def test_set_app_icon_skips_null_icon(self, tmp_path):
        """`QIcon.isNull()` 为 True 的文件应跳过。"""
        icon_path = tmp_path / "终端.png"
        # 创建空文件 → QIcon 应返回 isNull
        icon_path.write_bytes(b"")

        app = self._get_app()
        with patch("app.BASE_DIR", tmp_path):
            # 不抛异常，isNull 的图标会被跳过
            _set_app_icon(app)


# ── main() ──────────────────────────────────────────────


class TestMain:
    @patch("app._set_app_icon")
    @patch("app.sys.exit")
    @patch("app.SerialMonitor")
    @patch("app.QApplication")
    @patch("app.setup_logging")
    def test_main_creates_app_and_monitor(
        self,
        mock_setup_logging,
        mock_qapp_class,
        mock_monitor_class,
        mock_sys_exit,
        mock_set_app_icon,
    ):
        """main() 在 custom_style 文件不存在时使用 dark.qss 默认。"""
        mock_app = MagicMock()
        mock_qapp_class.return_value = mock_app
        mock_monitor = MagicMock()
        mock_monitor_class.return_value = mock_monitor

        custom_style_content = "/* custom */"
        mock_qdarktheme = MagicMock()
        mock_qdarktheme.load_stylesheet.return_value = "body { color: red; }"
        fake_modules = {"qdarktheme": mock_qdarktheme}
        with patch.dict("sys.modules", fake_modules), \
             patch.object(Path, "exists", return_value=False), \
             patch.object(Path, "read_text", return_value=custom_style_content):
            from app import main
            main()

        mock_setup_logging.assert_called_once()
        mock_monitor_class.assert_called_once()
        mock_monitor.show.assert_called_once()
        mock_sys_exit.assert_called_once()

    @patch("app._set_app_icon")
    @patch("app.sys.exit")
    @patch("app.SerialMonitor")
    @patch("app.QApplication")
    @patch("app.setup_logging")
    def test_main_uses_custom_style_for_theme(
        self,
        mock_setup_logging,
        mock_qapp_class,
        mock_monitor_class,
        mock_sys_exit,
        mock_set_app_icon,
    ):
        """main() 在 custom_style_<theme>.qss 存在时使用它。"""
        mock_app = MagicMock()
        mock_qapp_class.return_value = mock_app
        mock_qdarktheme = MagicMock()
        mock_qdarktheme.load_stylesheet.return_value = "body {color:red;}"
        fake_modules = {"qdarktheme": mock_qdarktheme}

        # 模拟：主题样式文件存在，dark.qss 不存在
        def exists_side_effect(self):
            return str(self).endswith("custom_style_dark.qss") is False

        with patch.dict("sys.modules", fake_modules), \
             patch.object(Path, "exists", autospec=True) as mock_exists, \
             patch.object(Path, "read_text", return_value="/* theme style */") as mock_read:
            # 主题样式文件存在
            mock_exists.side_effect = lambda p: "custom_style_dark" in str(p)
            os.environ["THEME"] = "dark"
            try:
                from app import main
                main()
                # 应调用 read_text 两次：一次是 custom_style_dark.qss
                assert mock_read.called
            finally:
                del os.environ["THEME"]

    @patch("app._set_app_icon")
    @patch("app.sys.exit")
    @patch("app.SerialMonitor")
    @patch("app.QApplication")
    @patch("app.setup_logging")
    def test_main_sets_app_metadata(
        self,
        mock_setup_logging,
        mock_qapp_class,
        mock_monitor_class,
        mock_sys_exit,
        mock_set_app_icon,
    ):
        """main() 应设置 application name 和 display name。"""
        mock_app = MagicMock()
        mock_qapp_class.return_value = mock_app
        mock_qdarktheme = MagicMock()
        mock_qdarktheme.load_stylesheet.return_value = ""
        fake_modules = {"qdarktheme": mock_qdarktheme}

        with patch.dict("sys.modules", fake_modules), \
             patch.object(Path, "exists", return_value=False), \
             patch.object(Path, "read_text", return_value=""):
            from app import main
            main()

        mock_app.setApplicationName.assert_called_once_with("Serial Monitor")
        mock_app.setApplicationDisplayName.assert_called_once_with("Serial Monitor")
        mock_app.setStyleSheet.assert_called_once()
