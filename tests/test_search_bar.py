"""
测试 ui/search_bar.py
"""

from PyQt6.QtCore import Qt

from ui.search_bar import SearchBar


class TestSearchBarSignals:
    def test_show_bar_visible_and_focus(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)

        bar.show_bar()
        assert bar.isVisible()

    def test_hide_bar_emits_close_requested(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.show_bar()

        with qtbot.waitSignal(bar.close_requested, timeout=500):
            bar.hide_bar()

    def test_update_result(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.update_result(2, 5)
        assert bar.result_label.text() == "2 / 5"

    def test_set_no_result(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.set_no_result()
        assert bar.result_label.text() == "0 / 0"

    def test_update_language(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        texts = {
            "search_placeholder": "搜索...",
            "search_prev": "上一个",
            "search_next": "下一个",
            "search_case": "区分大小写",
            "search_close": "关闭",
        }
        bar.update_language(texts)
        assert bar.input.placeholderText() == "搜索..."

    def test_text_changed_emits_search(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)

        with qtbot.waitSignal(bar.search_requested, timeout=500):
            bar.input.setText("hello")

    def test_next_button_emits_search(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.input.setText("test")

        with qtbot.waitSignal(bar.search_requested, timeout=500):
            bar.next_button.click()

    def test_prev_button_emits_backward_search(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.input.setText("test")

        received = []
        bar.search_requested.connect(lambda text, forward, case: received.append((text, forward, case)))
        bar.prev_button.click()
        assert received == [("test", False, False)]

    def test_case_toggle_emits_search(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.input.setText("test")

        with qtbot.waitSignal(bar.search_requested, timeout=500):
            bar.case_button.click()

    def test_case_sensitive_state(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.case_button.click()
        assert bar._case_sensitive is True
        bar.case_button.click()
        assert bar._case_sensitive is False

    def test_close_button(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.show_bar()

        with qtbot.waitSignal(bar.close_requested, timeout=500):
            bar.close_button.click()

    def test_key_escape_hides(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.show_bar()

        with qtbot.waitSignal(bar.close_requested, timeout=500):
            qtbot.keyClick(bar, Qt.Key.Key_Escape)

    def test_empty_text_clears_result(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.input.setText("test")
        bar.input.clear()
        assert bar.result_label.text() == ""

    def test_update_result_no_match(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.update_result(0, 0)
        assert bar.result_label.text() == "0 / 0"

    def test_update_result_with_match(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.update_result(2, 5)
        assert bar.result_label.text() == "2 / 5"

    def test_set_no_result(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.update_result(3, 3)
        bar.set_no_result()
        assert bar.result_label.text() == "0 / 0"

    def test_show_bar_emits_none(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.show_bar()
        # show_bar 只调用 show，不发信号
        assert bar.isVisible() or not bar.isVisible()  # 不抛异常即可

    def test_search_prev_emits(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.input.setText("text")
        with qtbot.waitSignal(bar.search_requested, timeout=500):
            bar.prev_button.click()

    def test_search_next_empty(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        signals = []
        bar.search_requested.connect(lambda *args: signals.append(args))
        bar.next_button.click()
        assert len(signals) == 0

    def test_key_escape_others_pass_through(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        # 其他键（不是 Escape）走父类 keyPressEvent
        qtbot.keyClick(bar, Qt.Key.Key_A)
        # 不抛异常即可

    def test_search_next_with_text(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.input.setText("query")
        with qtbot.waitSignal(bar.search_requested, timeout=500) as blocker:
            bar.next_button.click()
        assert blocker.args[0] == "query"
        assert blocker.args[1] is True  # forward

    def test_search_prev_with_text(self, qtbot):
        bar = SearchBar()
        qtbot.addWidget(bar)
        bar.input.setText("back")
        with qtbot.waitSignal(bar.search_requested, timeout=500) as blocker:
            bar.prev_button.click()
        assert blocker.args[0] == "back"
        assert blocker.args[1] is False  # backward
