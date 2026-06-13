from __future__ import annotations

from parallel_agents import __version__
from parallel_agents.desktop._qt import (
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    Signal,
)


class Sidebar(QFrame):
    section_selected = Signal(str)

    def __init__(self, sections: list[tuple[str, str]]) -> None:
        super().__init__()
        self.setObjectName("Sidebar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("PARALLEL AGENTS OFFICE")
        header.setObjectName("SidebarHeader")
        layout.addWidget(header)

        self._buttons: dict[str, QPushButton] = {}
        for label, key in sections:
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked=False, k=key: self.select(k))
            layout.addWidget(btn)
            self._buttons[key] = btn

        layout.addItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        )

        footer = QLabel(f"v{__version__} · local")
        footer.setObjectName("SidebarHeader")
        layout.addWidget(footer)

    def select(self, key: str) -> None:
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)
        self.section_selected.emit(key)

    def current_label(self) -> str:
        for button in self._buttons.values():
            if button.isChecked():
                return button.text()
        return "Command Center"
