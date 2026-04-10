"""
搜索栏组件

提供内嵌式搜索栏，支持上/下查找、大小写敏感、匹配计数显示。
Ctrl+F 打开，Esc 关闭。

Copyright (C) 2026 cpevor. Licensed under GPL v3.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


class SearchBar(QFrame):
    """内嵌搜索栏组件。"""

    search_requested = pyqtSignal(str, bool, bool)  # text, forward, case_sensitive
    close_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._case_sensitive: bool = False
        self._init_ui()

    def _init_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(4)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Search...")
        self.input.setClearButtonEnabled(True)
        self.input.textChanged.connect(self._on_text_changed)
        self.input.returnPressed.connect(self._on_return_pressed)

        self.prev_button = QPushButton("▲")
        self.prev_button.setFixedSize(28, 28)
        self.prev_button.setToolTip("Previous (Shift+Enter)")
        self.prev_button.clicked.connect(self._search_prev)

        self.next_button = QPushButton("▼")
        self.next_button.setFixedSize(28, 28)
        self.next_button.setToolTip("Next (Enter)")
        self.next_button.clicked.connect(self._search_next)

        self.case_button = QPushButton("Aa")
        self.case_button.setFixedSize(28, 28)
        self.case_button.setCheckable(True)
        self.case_button.setToolTip("Case sensitive")
        self.case_button.clicked.connect(self._toggle_case)

        self.result_label = QLabel("")
        self.result_label.setFixedWidth(80)
        self.result_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(28, 28)
        self.close_button.setToolTip("Close (Esc)")
        self.close_button.clicked.connect(self._on_close)

        layout.addWidget(self.input)
        layout.addWidget(self.prev_button)
        layout.addWidget(self.next_button)
        layout.addWidget(self.case_button)
        layout.addWidget(self.result_label)
        layout.addWidget(self.close_button)

        self.hide()

    def show_bar(self) -> None:
        self.show()
        self.input.setFocus()
        self.input.selectAll()

    def hide_bar(self) -> None:
        self.hide()
        self.close_requested.emit()

    def update_language(self, texts: dict[str, str]) -> None:
        self.input.setPlaceholderText(texts.get("search_placeholder", "Search..."))
        self.prev_button.setToolTip(texts.get("search_prev", "Previous"))
        self.next_button.setToolTip(texts.get("search_next", "Next"))
        self.case_button.setToolTip(texts.get("search_case", "Case sensitive"))
        self.close_button.setToolTip(texts.get("search_close", "Close"))

    def update_result(self, current: int, total: int) -> None:
        if total == 0:
            self.result_label.setText("0 / 0")
        else:
            self.result_label.setText(f"{current} / {total}")

    def set_no_result(self) -> None:
        self.result_label.setText("0 / 0")

    def _on_text_changed(self, text: str) -> None:
        if text:
            self.search_requested.emit(text, True, self._case_sensitive)
        else:
            self.result_label.setText("")

    def _on_return_pressed(self) -> None:
        text = self.input.text()
        if text:
            shift = (
                self.input.queryKeyboardModifiers() & Qt.KeyboardModifier.ShiftModifier
            )
            self.search_requested.emit(text, not shift, self._case_sensitive)

    def _search_next(self) -> None:
        text = self.input.text()
        if text:
            self.search_requested.emit(text, True, self._case_sensitive)

    def _search_prev(self) -> None:
        text = self.input.text()
        if text:
            self.search_requested.emit(text, False, self._case_sensitive)

    def _toggle_case(self, checked: bool) -> None:
        self._case_sensitive = checked
        text = self.input.text()
        if text:
            self.search_requested.emit(text, True, self._case_sensitive)

    def _on_close(self) -> None:
        self.hide_bar()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide_bar()
        else:
            super().keyPressEvent(event)
