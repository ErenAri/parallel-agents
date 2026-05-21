from __future__ import annotations

from parallel_agents.desktop._qt import QLabel, QVBoxLayout, QWidget


class Page(QWidget):
    """Common page chrome: header + subtitle + body container."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        header = QLabel(title)
        header.setObjectName("PageHeader")
        self._outer.addWidget(header)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("PageSubtitle")
            sub.setWordWrap(True)
            self._outer.addWidget(sub)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(32, 8, 32, 24)
        self.body_layout.setSpacing(16)
        self._outer.addWidget(self.body, stretch=1)
