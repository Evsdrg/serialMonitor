"""
测试 ui/dialogs.py
"""

from PyQt6.QtWidgets import QDialog

from ui.dialogs import HelpDialog, QuickSendItemDialog


class TestHelpDialog:
    def test_dialog_initialization(self, qtbot):
        dialog = HelpDialog(language="zh")
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "使用说明"

    def test_dialog_english(self, qtbot):
        dialog = HelpDialog(language="en")
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Help"


class TestQuickSendItemDialog:
    def test_default_data(self, qtbot):
        dialog = QuickSendItemDialog(language="zh")
        qtbot.addWidget(dialog)

        content, is_hex, auto_checksum, start, end_mode, line_ending = dialog.get_data()
        assert content == ""
        assert is_hex is False
        assert auto_checksum is False
        assert start == 1
        assert end_mode == 0

    def test_initial_values(self, qtbot):
        dialog = QuickSendItemDialog(
            language="zh",
            content="AA BB",
            is_hex=True,
            auto_checksum=True,
            checksum_start=2,
            checksum_end_mode=1,
            line_ending="\n",
        )
        qtbot.addWidget(dialog)

        content, is_hex, auto_checksum, start, end_mode, line_ending = dialog.get_data()
        assert content == "AA BB"
        assert is_hex is True
        assert auto_checksum is True
        assert start == 2
        assert end_mode == 1
        assert line_ending == "\n"

    def test_window_title(self, qtbot):
        dialog = QuickSendItemDialog(language="zh")
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "编辑条目"

    def test_window_title_english(self, qtbot):
        dialog = QuickSendItemDialog(language="en")
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == "Edit Item"

    def test_line_ending_cr(self, qtbot):
        dialog = QuickSendItemDialog(language="zh", line_ending="\r")
        qtbot.addWidget(dialog)

        _, _, _, _, _, line_ending = dialog.get_data()
        assert line_ending == "\r"
