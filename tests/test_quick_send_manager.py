"""
测试 quick_send_manager.py
"""

from unittest.mock import MagicMock, call, patch

import pytest

from core.payload_sender import PayloadRequest, SendResult, SendStatus
from ui.quick_send_manager import QuickSendManager


@pytest.fixture
def main_window():
    mw = MagicMock()
    mw.language = "zh"
    mw.is_connected.return_value = True
    mw.write_data.return_value = True
    mw.send_payload.return_value = SendResult(SendStatus.SENT, b"hello")
    return mw


@pytest.fixture
def manager(main_window):
    return QuickSendManager(main_window)


class TestQuickSendLifecycle:
    """P1: 关闭必须停掉顺序发送定时器；断连时不得弹出模态风暴"""

    def test_close_stops_sequence_timer(self, manager):
        panel = MagicMock()
        manager.panel = panel

        manager.close()

        panel.stop_sequence_send.assert_called_once()
        panel.close.assert_called_once()

    def test_disconnected_send_stops_sequence(self, manager, main_window):
        panel = MagicMock()
        manager.panel = panel
        main_window.send_payload.return_value = SendResult(SendStatus.NOT_CONNECTED)

        with patch("ui.quick_send_manager.QMessageBox.warning") as warning:
            manager.send_item("AT", False, False)

        # 首次失败即停队列，后续待发项不会再各弹一个模态框
        panel.stop_sequence_send.assert_called_once()
        assert warning.call_count == 1


class TestQuickSendManagerInit:
    def test_initial_panel_none(self, manager):
        assert manager.panel is None

    def test_main_window_stored(self, manager, main_window):
        assert manager.main_window is main_window


class TestQuickSendManagerTogglePanel:
    def test_toggle_creates_panel(self, manager, main_window):
        with patch("ui.quick_send_manager.QuickSendPanel") as MockPanel:
            mock_panel = MagicMock()
            MockPanel.return_value = mock_panel
            manager.toggle_panel()
            assert manager.panel is mock_panel
            MockPanel.assert_called_once_with(None, language="zh")

    def test_toggle_shows_panel(self, manager, main_window):
        with patch("ui.quick_send_manager.QuickSendPanel") as MockPanel:
            mock_panel = MagicMock()
            mock_panel.isVisible.return_value = False
            MockPanel.return_value = mock_panel
            manager.toggle_panel()
            manager.toggle_panel()
            mock_panel.show.assert_called()

    def test_toggle_hides_panel(self, manager, main_window):
        with patch("ui.quick_send_manager.QuickSendPanel") as MockPanel:
            mock_panel = MagicMock()
            mock_panel.isVisible.return_value = True
            MockPanel.return_value = mock_panel
            manager.toggle_panel()
            manager.toggle_panel()
            mock_panel.hide.assert_called()

    def test_toggle_positions_panel(self, manager, main_window):
        with patch("ui.quick_send_manager.QuickSendPanel") as MockPanel, \
             patch("ui.quick_send_manager.QTimer") as MockTimer:
            mock_panel = MagicMock()
            mock_panel.isVisible.return_value = False
            MockPanel.return_value = mock_panel
            manager.toggle_panel()
            manager.toggle_panel()
            MockTimer.singleShot.assert_called()


class TestQuickSendManagerUpdateLanguage:
    def test_update_language_delegates(self, manager):
        manager.panel = MagicMock()
        manager.update_language("en")
        manager.panel.update_language.assert_called_once_with("en")

    def test_update_language_no_panel(self, manager):
        manager.update_language("en")  # should not raise


class TestQuickSendManagerClose:
    def test_close_delegates(self, manager):
        manager.panel = MagicMock()
        manager.close()
        manager.panel.close.assert_called_once()

    def test_close_no_panel(self, manager):
        manager.close()  # should not raise


class TestQuickSendManagerSaveSettings:
    def test_save_settings_delegates(self, manager):
        manager.panel = MagicMock()
        manager.panel.get_items.return_value = [{"content": "test"}]
        with patch("ui.quick_send_manager.ConfigManager.save_quick_sends") as mock_save:
            manager.save_settings()
            mock_save.assert_called_once_with([{"content": "test"}])

    def test_save_settings_no_panel(self, manager):
        manager.save_settings()  # should not raise


class TestQuickSendManagerCreatePanel:
    def test_create_panel_loads_items(self, manager, main_window):
        with patch("ui.quick_send_manager.QuickSendPanel") as MockPanel, \
             patch("ui.quick_send_manager.ConfigManager.load_quick_sends", return_value=[{"content": "hi"}]):
            mock_panel = MagicMock()
            MockPanel.return_value = mock_panel
            manager.create_panel()
            mock_panel.load_items.assert_called_once_with([{"content": "hi"}])

    def test_create_panel_no_items(self, manager, main_window):
        with patch("ui.quick_send_manager.QuickSendPanel") as MockPanel, \
             patch("ui.quick_send_manager.ConfigManager.load_quick_sends", return_value=[]):
            mock_panel = MagicMock()
            MockPanel.return_value = mock_panel
            manager.create_panel()
            mock_panel.load_items.assert_not_called()


class TestQuickSendManagerPositionPanel:
    def test_position_panel_normal(self, manager, main_window):
        manager.panel = MagicMock()
        manager.panel.isVisible.return_value = True
        mock_geo = MagicMock()
        mock_geo.right.return_value = 800
        mock_geo.top.return_value = 100
        mock_geo.x.return_value = 100
        mock_geo.y.return_value = 100
        main_window.frameGeometry.return_value = mock_geo

        manager._position_panel()
        manager.panel.move.assert_called_once_with(810, 100)

    def test_position_panel_at_origin(self, manager, main_window):
        manager.panel = MagicMock()
        manager.panel.isVisible.return_value = True
        mock_geo = MagicMock()
        mock_geo.right.return_value = 1920
        mock_geo.top.return_value = 0
        mock_geo.x.return_value = 0
        mock_geo.y.return_value = 0
        main_window.frameGeometry.return_value = mock_geo

        mock_screen = MagicMock()
        mock_screen_geo = MagicMock()
        mock_screen_geo.width.return_value = 1920
        mock_screen_geo.height.return_value = 1080
        mock_screen.availableGeometry.return_value = mock_screen_geo
        main_window.screen.return_value = mock_screen

        manager._position_panel()
        expected_x = 1920 * 2 // 3
        expected_y = 1080 // 4
        manager.panel.move.assert_called_once_with(expected_x, expected_y)

    def test_position_panel_no_screen(self, manager, main_window):
        manager.panel = MagicMock()
        manager.panel.isVisible.return_value = True
        mock_geo = MagicMock()
        mock_geo.right.return_value = 0
        mock_geo.top.return_value = 0
        mock_geo.x.return_value = 0
        mock_geo.y.return_value = 0
        main_window.frameGeometry.return_value = mock_geo
        main_window.screen.return_value = None

        manager._position_panel()
        manager.panel.move.assert_called_once_with(10, 0)

    def test_position_panel_no_panel(self, manager, main_window):
        manager.panel = None
        manager._position_panel()  # should not raise


class TestQuickSendManagerSendItem:
    def test_send_item_not_open(self, manager, main_window):
        main_window.send_payload.return_value = SendResult(
            SendStatus.NOT_CONNECTED
        )
        with patch("ui.quick_send_manager.QMessageBox") as mock_msg:
            manager.send_item("hello", False, False)
            mock_msg.warning.assert_called()

    def test_send_item_success(self, manager, main_window):
        manager.send_item("hello", False, False)

        request = main_window.send_payload.call_args.args[0]
        assert request == PayloadRequest(text="hello")
        main_window.append_to_terminal.assert_not_called()

    def test_send_item_with_checksum(self, manager, main_window):
        manager.send_item(
            "hello", False, True, checksum_start=1, checksum_end_mode=0
        )

        request = main_window.send_payload.call_args.args[0]
        assert request.auto_checksum is True
        assert request.checksum_start == 1
        assert request.checksum_end_mode == 0

    def test_send_item_checksum_invalid_range(self, manager, main_window):
        main_window.send_payload.return_value = SendResult(
            SendStatus.INVALID_CHECKSUM_RANGE, b"hello"
        )
        manager.send_item(
            "hello", False, True, checksum_start=5, checksum_end_mode=1
        )

        main_window.append_to_terminal.assert_called()

    def test_send_item_write_failure(self, manager, main_window):
        main_window.send_payload.return_value = SendResult(
            SendStatus.WRITE_FAILED, b"hello"
        )
        main_window.connection_error.return_value = "port busy"

        manager.send_item("hello", False, False)

        main_window.append_to_terminal.assert_called()

    def test_send_item_with_line_ending(self, manager, main_window):
        manager.send_item("cmd", False, False, line_ending="\r\n")

        request = main_window.send_payload.call_args.args[0]
        assert request.line_ending == b"\r\n"

    def test_send_item_exception(self, manager, main_window):
        main_window.send_payload.return_value = SendResult(
            SendStatus.INVALID_PAYLOAD
        )
        manager.send_item("ZZ", True, False)

        main_window.append_to_terminal.assert_called()
