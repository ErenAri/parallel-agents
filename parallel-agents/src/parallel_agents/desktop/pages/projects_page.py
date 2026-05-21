from __future__ import annotations

from pathlib import Path

from parallel_agents.desktop._qt import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    Qt,
    Signal,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService


class ProjectsPage(Page):
    project_opened = Signal(object)

    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Projects",
            subtitle="Open an existing project folder or initialize a new local office workspace.",
        )
        self.engine = engine

        actions = QHBoxLayout()
        open_btn = QPushButton("Open Project Folder…")
        open_btn.setObjectName("Primary")
        open_btn.clicked.connect(self._open_project)

        new_btn = QPushButton("Initialize New Office…")
        new_btn.clicked.connect(self._init_project)

        actions.addWidget(open_btn)
        actions.addWidget(new_btn)
        actions.addStretch(1)
        self.body_layout.addLayout(actions)

        self.current_card = QFrame()
        self.current_card.setObjectName("Card")
        card_layout = QVBoxLayout(self.current_card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        self.current_label = QLabel("No project selected.")
        self.current_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.current_meta = QLabel("")
        self.current_meta.setStyleSheet("color: #8a90a2;")
        card_layout.addWidget(self.current_label)
        card_layout.addWidget(self.current_meta)
        self.body_layout.addWidget(self.current_card)

        self.recent_label = QLabel("Recent Runs")
        self.recent_label.setStyleSheet("font-weight: 600; padding-top: 8px;")
        self.body_layout.addWidget(self.recent_label)

        self.recent_list = QListWidget()
        self.body_layout.addWidget(self.recent_list, stretch=1)

    def _open_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select project folder")
        if not path:
            return
        info = self.engine.open_project(path)
        self._refresh(info)

    def _init_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select folder for new office")
        if not path:
            return
        name, ok = QInputDialog.getText(
            self, "Project name", "Project name:", text=Path(path).name
        )
        if not ok:
            return
        try:
            info = self.engine.init_project(path, name=name or None)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Init failed", str(exc))
            return
        self._refresh(info)

    def _refresh(self, info) -> None:
        self.current_label.setText(info.name)
        self.current_meta.setText(
            f"{info.root}\n{info.run_count} run(s) · office: {info.office_dir}"
        )
        self.recent_list.clear()
        for run in self.engine.list_runs():
            item = QListWidgetItem(f"{run['id']}   {run.get('created_at', '')}")
            item.setData(Qt.ItemDataRole.UserRole, run["id"])
            self.recent_list.addItem(item)
        self.project_opened.emit(info)
