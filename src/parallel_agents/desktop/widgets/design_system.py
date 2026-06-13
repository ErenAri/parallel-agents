from __future__ import annotations

from parallel_agents.desktop._qt import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Card(QFrame):
    def __init__(self, *, hero: bool = False) -> None:
        super().__init__()
        self.setObjectName("HeroCard" if hero else "Card")


class SectionHeader(QWidget):
    def __init__(self, title: str, hint: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("SectionHeader")
        layout.addWidget(title_label)

        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("SectionHint")
            hint_label.setWordWrap(True)
            layout.addWidget(hint_label)


class StatCard(Card):
    def __init__(self, label: str, value: str = "-", hint: str = "") -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.label_label = QLabel(label)
        self.label_label.setObjectName("StatLabel")
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("CardMeta")
        self.hint_label.setWordWrap(True)

        layout.addWidget(self.value_label)
        layout.addWidget(self.label_label)
        if hint:
            layout.addWidget(self.hint_label)

    def set_value(self, value: str, hint: str | None = None) -> None:
        self.value_label.setText(value)
        if hint is not None:
            self.hint_label.setText(hint)
            self.hint_label.setVisible(bool(hint))


class StatusLine(QWidget):
    def __init__(self, label: str, status: str = "idle", detail: str = "") -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.dot = QLabel("●")
        self.dot.setObjectName(_dot_object(status))
        self.label = QLabel(label)
        self.label.setObjectName("CardTitle")
        self.detail = QLabel(detail)
        self.detail.setObjectName("CardMeta")
        self.detail.setWordWrap(True)

        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        layout.addWidget(self.detail, stretch=1)

    def set_status(self, status: str, detail: str = "") -> None:
        self.dot.setObjectName(_dot_object(status))
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)
        self.detail.setText(detail)


class ActionRow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(8)

    def add_action(
        self,
        label: str,
        callback,
        *,
        primary: bool = False,
        danger: bool = False,
    ) -> QPushButton:
        button = QPushButton(label)
        if primary:
            button.setObjectName("Primary")
        elif danger:
            button.setObjectName("Danger")
        button.clicked.connect(callback)
        self.layout.addWidget(button)
        return button

    def add_stretch(self) -> None:
        self.layout.addStretch(1)


def _dot_object(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {"running", "warning", "starting"}:
        return "StatusDotRunning"
    if normalized in {"done", "healthy", "ok", "success", "running_ok"}:
        return "StatusDotDone"
    if normalized in {"error", "failed", "unhealthy"}:
        return "StatusDotError"
    return "StatusDotIdle"
