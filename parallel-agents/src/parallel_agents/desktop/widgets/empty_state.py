"""Centered empty-state widget for pages that have no data to show yet."""

from __future__ import annotations

from collections.abc import Callable

from parallel_agents.desktop._qt import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
)


class EmptyState(QWidget):
    def __init__(
        self,
        title: str,
        hint: str = "",
        action_label: str | None = None,
        action: Callable[[], None] | None = None,
        glyph: str = "·",
    ) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)

        card = QWidget()
        card.setObjectName("EmptyStateCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(12)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        glyph_label = QLabel(glyph)
        glyph_label.setObjectName("EmptyStateGlyph")
        glyph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(glyph_label)

        title_label = QLabel(title)
        title_label.setObjectName("EmptyStateTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title_label)

        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("EmptyStateHint")
            hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint_label.setWordWrap(True)
            card_layout.addWidget(hint_label)

        if action_label and action is not None:
            btn = QPushButton(action_label)
            btn.setObjectName("Primary")
            btn.clicked.connect(action)
            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            btn_row.addWidget(btn)
            btn_row.addStretch(1)
            card_layout.addLayout(btn_row)

        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(2)
