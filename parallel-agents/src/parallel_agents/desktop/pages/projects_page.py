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
from parallel_agents.desktop.services.history import HistoryStore


class ProjectsPage(Page):
    project_opened = Signal(object)

    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Projects",
            subtitle="Open an existing project folder or initialize a new local office workspace.",
        )
        self.engine = engine
        self.history = HistoryStore()

        actions = QHBoxLayout()
        open_btn = QPushButton("Open Project Folder...")
        open_btn.setObjectName("Primary")
        open_btn.clicked.connect(self._open_project)

        new_btn = QPushButton("Initialize New Office...")
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
        self.current_stats = QLabel("")
        self.current_stats.setStyleSheet("color: #8a90a2;")
        card_layout.addWidget(self.current_label)
        card_layout.addWidget(self.current_meta)
        card_layout.addWidget(self.current_stats)
        self.body_layout.addWidget(self.current_card)

        recent_projects_title = QLabel("Recent Project Folders")
        recent_projects_title.setStyleSheet("font-weight: 600; padding-top: 8px;")
        self.body_layout.addWidget(recent_projects_title)

        recent_project_actions = QHBoxLayout()
        open_recent_btn = QPushButton("Open Selected Recent")
        open_recent_btn.clicked.connect(self._open_selected_recent)
        clear_recent_btn = QPushButton("Clear Recent")
        clear_recent_btn.clicked.connect(self._clear_recent_projects)
        recent_project_actions.addWidget(open_recent_btn)
        recent_project_actions.addWidget(clear_recent_btn)
        recent_project_actions.addStretch(1)
        self.body_layout.addLayout(recent_project_actions)

        self.recent_projects_list = QListWidget()
        self.recent_projects_list.itemDoubleClicked.connect(
            lambda _item: self._open_selected_recent()
        )
        self.body_layout.addWidget(self.recent_projects_list)

        self.recent_label = QLabel("Recent Runs")
        self.recent_label.setStyleSheet("font-weight: 600; padding-top: 8px;")
        self.body_layout.addWidget(self.recent_label)

        self.recent_list = QListWidget()
        self.body_layout.addWidget(self.recent_list, stretch=1)
        self._refresh_recent_projects()

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

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._refresh_recent_projects()
        current = self.engine.current_project()
        if current is not None:
            self._refresh(current)

    def _open_selected_recent(self) -> None:
        item = self.recent_projects_list.currentItem()
        if item is None:
            QMessageBox.information(
                self, "Recent projects", "Select a recent project first."
            )
            return
        root_text = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
        if not root_text:
            return
        root = Path(root_text)
        if not root.exists():
            QMessageBox.warning(self, "Missing folder", f"Path no longer exists:\n{root}")
            return
        info = self.engine.open_project(root)
        self._refresh(info)

    def _clear_recent_projects(self) -> None:
        self.history.clear("project_root")
        self._refresh_recent_projects()

    def _refresh(self, info) -> None:
        self.history.add("project_root", str(info.root), limit=12)
        self._refresh_recent_projects()
        self.current_label.setText(info.name)
        home = self.engine.workspace_home()
        self.current_meta.setText(f"{info.root}\nOffice: {info.office_dir}")
        self.current_stats.setText(
            "Runs: "
            f"{home.run_count}  |  Artifacts: {home.artifact_count}  |  Pending approvals: {home.pending_approval_count}"
            + (f"  |  Branch: {home.current_branch}" if home.current_branch else "")
        )
        self.recent_list.clear()
        for run in self.engine.list_runs():
            item = QListWidgetItem(f"{run['id']}   {run.get('created_at', '')}")
            item.setData(Qt.ItemDataRole.UserRole, run["id"])
            self.recent_list.addItem(item)
        self.project_opened.emit(info)

    def _refresh_recent_projects(self) -> None:
        self.recent_projects_list.clear()
        roots = self.history.get("project_root", limit=12)
        if not roots:
            placeholder = QListWidgetItem("No recent projects yet")
            placeholder.setFlags(placeholder.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.recent_projects_list.addItem(placeholder)
            return
        for raw in roots:
            root = Path(raw)
            exists = root.exists()
            label = str(root) if exists else f"{root}  [missing]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(root))
            if not exists:
                item.setForeground(self.palette().mid())
            self.recent_projects_list.addItem(item)
