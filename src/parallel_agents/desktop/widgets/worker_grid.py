from __future__ import annotations

from parallel_agents.desktop._qt import (
    QFrame,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

WORKER_ROLES = [
    "planner",
    "splitter",
    "security",
    "test",
    "perf",
    "devops",
    "arch",
    "docs",
    "code",
    "review",
    "judge",
]

STATUS_STYLE = {
    "idle": "WorkerStatusIdle",
    "running": "WorkerStatusRunning",
    "done": "WorkerStatusDone",
    "error": "WorkerStatusError",
}


class WorkerTile(QFrame):
    def __init__(self, role: str) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.role = role

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(4)

        self.name_label = QLabel(role.upper())
        self.name_label.setStyleSheet(
            "font-weight: 600; letter-spacing: 0.8px; font-size: 11px; color: #c9cdd6;"
        )

        self.status_label = QLabel("idle")
        self.status_label.setObjectName(STATUS_STYLE["idle"])

        self.detail_label = QLabel("Waiting for run")
        self.detail_label.setStyleSheet("color: #8a90a2; font-size: 12px;")
        self.detail_label.setWordWrap(True)

        layout.addWidget(self.name_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.detail_label)

    def set_status(self, status: str, detail: str | None = None) -> None:
        self.status_label.setText(status)
        self.status_label.setObjectName(STATUS_STYLE.get(status, "WorkerStatusIdle"))
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        if detail is not None:
            self.detail_label.setText(detail)


class WorkerGrid(QWidget):
    def __init__(self, roles: list[str] | None = None) -> None:
        super().__init__()
        self.tiles: dict[str, WorkerTile] = {}

        roles = roles or WORKER_ROLES
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)

        cols = 4
        for i, role in enumerate(roles):
            tile = WorkerTile(role)
            self.tiles[role] = tile
            grid.addWidget(tile, i // cols, i % cols)

    def update_worker(self, role: str, status: str, detail: str | None = None) -> None:
        tile = self.tiles.get(role)
        if tile is not None:
            tile.set_status(status, detail)
