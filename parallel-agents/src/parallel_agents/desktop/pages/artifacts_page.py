from __future__ import annotations

import difflib
import json
from pathlib import Path

from parallel_agents.desktop._qt import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
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
        self.compare_btn = QPushButton("Compare Previous")
        self.compare_btn.clicked.connect(self._compare_previous)
        row.addWidget(self.compare_btn)
        self.clear_compare_btn = QPushButton("Clear Compare")
        self.clear_compare_btn.clicked.connect(self._show_selected)
        row.addWidget(self.clear_compare_btn)
        row.addStretch(1)
        self.body_layout.addLayout(row)

        self.compare_label = QLabel("")
        self.compare_label.setStyleSheet("color: #8a90a2; font-size: 12px;")
        self.body_layout.addWidget(self.compare_label)

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
        self.compare_label.setText("")
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
        self.compare_label.setText("")
        item = self.tree.currentItem()
        if item is None:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path is None:
            return
        self.viewer.show_path(path)

    def _compare_previous(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            QMessageBox.information(self, "Select artifact", "Select an artifact first.")
            return
        current_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(current_path, Path):
            QMessageBox.information(self, "Select artifact", "Pick an artifact row, not the run row.")
            return

        previous_path = self._find_previous_artifact(current_path)
        if previous_path is None:
            QMessageBox.information(
                self,
                "No previous version",
                f"No earlier run contains `{current_path.name}`.",
            )
            return

        current_text = _read_artifact_for_compare(current_path)
        previous_text = _read_artifact_for_compare(previous_path)
        diff = list(
            difflib.unified_diff(
                previous_text.splitlines(),
                current_text.splitlines(),
                fromfile=str(previous_path),
                tofile=str(current_path),
                lineterm="",
            )
        )
        if not diff:
            self.viewer.setPlainText("No changes between these two versions.")
        else:
            self.viewer.setPlainText("\n".join(diff))
        self.compare_label.setText(
            f"Comparing {current_path.parent.parent.name}/{current_path.name} "
            f"against {previous_path.parent.parent.name}/{previous_path.name}"
        )

    def _find_previous_artifact(self, current_path: Path) -> Path | None:
        runs = [entry["id"] for entry in self.engine.list_runs()]
        current_run = current_path.parent.parent.name
        if current_run not in runs:
            return None
        current_idx = runs.index(current_run)
        for run_id in runs[current_idx + 1 :]:
            for candidate in self.engine.list_artifacts(run_id):
                if candidate.name == current_path.name:
                    return candidate
        return None


def _read_artifact_for_compare(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() != ".json":
        return text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
