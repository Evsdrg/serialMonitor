"""
测试 ui/quick_send_panel.py
"""

from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog

from ui.quick_send_panel import QuickSendPanel


class TestQuickSendPanelItems:
    def test_add_item_to_list(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        panel.add_item_to_list("AT", is_hex=False, auto_checksum=False)
        assert panel.list_widget.count() == 1

    def test_add_hex_item_display(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        panel.add_item_to_list("AA BB", is_hex=True, auto_checksum=False)
        item = panel.list_widget.item(0)
        assert "HEX" in item.text()

    def test_add_item_with_checksum_display(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        panel.add_item_to_list("0102", is_hex=True, auto_checksum=True, checksum_start=1, checksum_end_mode=1)
        item = panel.list_widget.item(0)
        assert "CK" in item.text()

    def test_add_item_with_line_ending_lf(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        panel.add_item_to_list("AT", line_ending="\n")
        item = panel.list_widget.item(0)
        assert "LF" in item.text()

    def test_add_item_with_line_ending_crlf(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        panel.add_item_to_list("AT", line_ending="\r\n")
        item = panel.list_widget.item(0)
        assert "CRLF" in item.text()

    def test_get_items(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        panel.add_item_to_list("AT", is_hex=False, auto_checksum=False, checked=True)
        items = panel.get_items()
        assert len(items) == 1
        assert items[0]["content"] == "AT"
        assert items[0]["checked"] is True

    def test_load_items(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        items = [
            {"content": "test1", "is_hex": False, "auto_checksum": False, "checked": True},
            {"content": "test2", "is_hex": True, "auto_checksum": False, "checked": False},
        ]
        panel.load_items(items)
        assert panel.list_widget.count() == 2
        assert panel.list_widget.item(0).checkState() == Qt.CheckState.Checked
        assert panel.list_widget.item(1).checkState() == Qt.CheckState.Unchecked

    def test_delete_item(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        panel.add_item_to_list("AT")
        panel.list_widget.setCurrentRow(0)
        panel._delete_item()
        assert panel.list_widget.count() == 0

    def test_send_selected_emits_signal(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        panel.add_item_to_list("AT", is_hex=False, auto_checksum=False)
        panel.list_widget.setCurrentRow(0)

        received = []
        panel.send_requested.connect(lambda *args: received.append(args))
        panel._send_selected()

        assert len(received) == 1
        assert received[0][0] == "AT"

    def test_send_item_emits_signal(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        panel.add_item_to_list("HEXDATA", is_hex=True, auto_checksum=True, checksum_start=2, checksum_end_mode=1, line_ending="\n")
        item = panel.list_widget.item(0)

        received = []
        panel.send_requested.connect(lambda *args: received.append(args))
        panel._send_item(item)

        assert len(received) == 1
        content, is_hex, auto_checksum, start, end_mode, line_ending = received[0]
        assert content == "HEXDATA"
        assert is_hex is True
        assert auto_checksum is True
        assert start == 2
        assert end_mode == 1
        assert line_ending == "\n"


class TestQuickSendPanelLanguage:
    def test_update_language(self, qtbot):
        panel = QuickSendPanel(language="en")
        qtbot.addWidget(panel)

        panel.update_language("zh")
        assert panel.language == "zh"
        assert panel.add_button.text() == "添加"

    def test_initial_language(self, qtbot):
        panel = QuickSendPanel(language="en")
        qtbot.addWidget(panel)
        assert panel.windowTitle() == "Quick Send Panel"

    def test_format_display_language_switch(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        text_zh = panel._format_display("AT", True, True, 1, 0, "")
        panel.language = "en"
        text_en = panel._format_display("AT", True, True, 1, 0, "")
        assert "末尾" in text_zh
        assert "End" in text_en


class TestQuickSendPanelActions:
    def test_delete_item(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel.add_item_to_list("test", checked=False)
        initial_count = panel.list_widget.count()
        panel.list_widget.setCurrentRow(0)
        panel._delete_item()
        assert panel.list_widget.count() == initial_count - 1

    def test_delete_item_none_selected(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel._delete_item()  # should not raise

    def test_send_item_emits_signal(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel.add_item_to_list("hello", is_hex=False, auto_checksum=False)

        signals = []
        panel.send_requested.connect(lambda *args: signals.append(args))

        item = panel.list_widget.item(0)
        panel._send_item(item)
        assert len(signals) == 1
        assert signals[0][0] == "hello"

    def test_send_item_no_data(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        from PyQt6.QtWidgets import QListWidgetItem
        empty_item = QListWidgetItem("empty")
        panel.list_widget.addItem(empty_item)
        signals = []
        panel.send_requested.connect(lambda *args: signals.append(args))
        panel._send_item(empty_item)
        assert len(signals) == 0

    def test_send_selected_no_item(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        signals = []
        panel.send_requested.connect(lambda *args: signals.append(args))
        panel._send_selected()
        assert len(signals) == 0

    def test_stop_sequence_send(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel.quick_send_timer.start(100)
        panel.send_checked_button.setEnabled(False)
        panel.stop_button.setEnabled(True)

        panel.stop_sequence_send()

        assert not panel.quick_send_timer.isActive()
        assert panel.quick_send_queue == []
        assert panel.send_checked_button.isEnabled()
        assert not panel.stop_button.isEnabled()

    def test_add_item_with_mocked_dialog(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        initial_count = panel.list_widget.count()

        mock_data = ("test_content", False, False, 1, 0, "")
        with patch("ui.quick_send_panel.QuickSendItemDialog") as MockDialog:
            mock_dialog = MagicMock()
            mock_dialog.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.get_data.return_value = mock_data
            MockDialog.return_value = mock_dialog
            panel._add_item()

        assert panel.list_widget.count() == initial_count + 1

    def test_get_items(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel.add_item_to_list("cmd", is_hex=False, checked=True)
        panel.add_item_to_list("A0", is_hex=True, checked=False)

        items = panel.get_items()
        assert len(items) == 2
        assert items[0]["content"] == "cmd"
        assert items[0]["checked"] is True
        assert items[1]["content"] == "A0"
        assert items[1]["checked"] is False

    def test_load_items(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel.add_item_to_list("old")
        assert panel.list_widget.count() == 1

        items = [
            {"content": "new1", "is_hex": False, "checked": True},
            {"content": "A0", "is_hex": True, "checked": False},
        ]
        panel.load_items(items)
        assert panel.list_widget.count() == 2
        assert panel.get_items()[0]["content"] == "new1"

    def test_start_sequence_send_no_checked(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel.add_item_to_list("item1", checked=False)

        with patch("ui.quick_send_panel.QMessageBox") as MockMsg:
            panel._start_sequence_send()
            MockMsg.information.assert_called_once()

    def test_start_sequence_send_with_checked(self, qtbot):
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel.add_item_to_list("item1", checked=True)

        with patch.object(panel.quick_send_timer, "start") as mock_start, \
             patch.object(panel, "_send_next_in_queue") as mock_send:
            panel._start_sequence_send()
            mock_send.assert_called_once()
            mock_start.assert_called_once()
            assert not panel.send_checked_button.isEnabled()
            assert panel.stop_button.isEnabled()

    def test_edit_item_accepted_updates_data(self, qtbot):
        """`_edit_item` 在用户接受对话框时应更新 item 数据。"""
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel.add_item_to_list(
            "old_content", is_hex=False, auto_checksum=False,
            checksum_start=1, checksum_end_mode=0, line_ending="",
        )
        item = panel.list_widget.item(0)

        new_data = ("new_content", True, True, 2, 1, "\r\n")
        with patch("ui.quick_send_panel.QuickSendItemDialog") as MockDialog:
            mock_dialog = MagicMock()
            mock_dialog.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.get_data.return_value = new_data
            MockDialog.return_value = mock_dialog
            panel._edit_item(item)

        updated = item.data(Qt.ItemDataRole.UserRole)
        assert updated["content"] == "new_content"
        assert updated["is_hex"] is True
        assert updated["auto_checksum"] is True
        assert updated["checksum_start"] == 2
        assert updated["checksum_end_mode"] == 1
        assert updated["line_ending"] == "\r\n"

    def test_edit_item_rejected_no_change(self, qtbot):
        """`_edit_item` 在用户取消对话框时不应修改 item。"""
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel.add_item_to_list("original", is_hex=False, auto_checksum=False)
        item = panel.list_widget.item(0)
        original_data = item.data(Qt.ItemDataRole.UserRole)

        with patch("ui.quick_send_panel.QuickSendItemDialog") as MockDialog:
            mock_dialog = MagicMock()
            mock_dialog.exec.return_value = QDialog.DialogCode.Rejected
            MockDialog.return_value = mock_dialog
            panel._edit_item(item)

        assert item.data(Qt.ItemDataRole.UserRole) == original_data

    def test_edit_item_no_data_returns_early(self, qtbot):
        """`_edit_item` 在 item 无数据时应直接返回。"""
        from PyQt6.QtWidgets import QListWidgetItem
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        item = QListWidgetItem("no data")
        panel.list_widget.addItem(item)

        with patch("ui.quick_send_panel.QuickSendItemDialog") as MockDialog:
            panel._edit_item(item)
            MockDialog.assert_not_called()

    def test_edit_item_passes_defaults_from_data(self, qtbot):
        """`_edit_item` 应将 item 的现有数据传给对话框。"""
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel.add_item_to_list(
            "test", is_hex=True, auto_checksum=True,
            checksum_start=3, checksum_end_mode=2, line_ending="\n",
        )
        item = panel.list_widget.item(0)

        with patch("ui.quick_send_panel.QuickSendItemDialog") as MockDialog:
            mock_dialog = MagicMock()
            mock_dialog.exec.return_value = QDialog.DialogCode.Rejected
            MockDialog.return_value = mock_dialog
            panel._edit_item(item)
            MockDialog.assert_called_once()
            call_kwargs = MockDialog.call_args.kwargs
            assert call_kwargs["content"] == "test"
            assert call_kwargs["is_hex"] is True
            assert call_kwargs["auto_checksum"] is True
            assert call_kwargs["checksum_start"] == 3
            assert call_kwargs["checksum_end_mode"] == 2
            assert call_kwargs["line_ending"] == "\n"

    def test_edit_item_handles_missing_default_fields(self, qtbot):
        """`_edit_item` 应处理缺少默认字段的情况。"""
        from PyQt6.QtWidgets import QListWidgetItem
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)

        item = QListWidgetItem("partial")
        item.setData(
            Qt.ItemDataRole.UserRole,
            {"content": "x", "is_hex": False, "auto_checksum": False},
        )
        panel.list_widget.addItem(item)

        with patch("ui.quick_send_panel.QuickSendItemDialog") as MockDialog:
            mock_dialog = MagicMock()
            mock_dialog.exec.return_value = QDialog.DialogCode.Rejected
            MockDialog.return_value = mock_dialog
            panel._edit_item(item)
            call_kwargs = MockDialog.call_args.kwargs
            assert call_kwargs["checksum_start"] == 1  # default
            assert call_kwargs["checksum_end_mode"] == 0  # default
            assert call_kwargs["line_ending"] == ""  # default

    def test_edit_item_updates_display_text(self, qtbot):
        """`_edit_item` 接受后应更新 item 的显示文本。"""
        panel = QuickSendPanel(language="zh")
        qtbot.addWidget(panel)
        panel.add_item_to_list("old", is_hex=False)
        item = panel.list_widget.item(0)
        old_text = item.text()

        new_data = ("brand_new", False, False, 1, 0, "")
        with patch("ui.quick_send_panel.QuickSendItemDialog") as MockDialog:
            mock_dialog = MagicMock()
            mock_dialog.exec.return_value = QDialog.DialogCode.Accepted
            mock_dialog.get_data.return_value = new_data
            MockDialog.return_value = mock_dialog
            panel._edit_item(item)

        assert item.text() != old_text
        assert "brand_new" in item.text()
