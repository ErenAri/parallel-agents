from __future__ import annotations

from parallel_agents.desktop._qt import (
    QHBoxLayout,
    QPushButton,
    QSplitter,
    Qt,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService
from parallel_agents.desktop.widgets.artifact_viewer import ArtifactViewer


class ArtifactsPage(Page):
    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Artifacts",
            subtitle="Browse briefs, RFCs, roadmaps, sprint plans, release checks, and PR summaries by run.",
        )
        self.engine = engine

        row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        row.addWidget(refresh)
        row.addStretch(1)
        self.body_layout.addLayout(row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Run / Artifact"])
        self.tree.itemSelectionChanged.connect(self._show_selected)
        splitter.addWidget(self.tree)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.viewer = ArtifactViewer()
        right_layout.addWidget(self.viewer, stretch=1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        self.body_layout.addWidget(splitter, stretch=1)

        self._refresh()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        self.tree.clear()
        if self.engine.current_project() is None:
            placeholder = QTreeWidgetItem(self.tree, ["Open a project to see artifacts"])
            placeholder.setDisabled(True)
            return
        for run in self.engine.list_runs():
            run_id = run["id"]
            run_item = QTreeWidgetItem(self.tree, [run_id])
            run_item.setData(0, Qt.ItemDataRole.UserRole + 1, run_id)
            for path in self.engine.list_artifacts(run_id):
                child = QTreeWidgetItem(run_item, [path.name])
                child.setData(0, Qt.ItemDataRole.UserRole, path)
            run_item.setExpanded(True)

    def focus_artifact(self, run_id: str, path) -> None:
        self._refresh()
        for i in range(self.tree.topLevelItemCount()):
            run_item = self.tree.topLevelItem(i)
            if run_item.data(0, Qt.ItemDataRole.UserRole + 1) != run_id:
                continue
            for j in range(run_item.childCount()):
                child = run_item.child(j)
                child_path = child.data(0, Qt.ItemDataRole.UserRole)
                if child_path is not None and str(child_path) == str(path):
                    self.tree.setCurrentItem(child)
                    return

    def _show_selected(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path is None:
            return
        self.viewer.show_path(path)
