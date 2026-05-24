from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from parallel_agents.desktop._qt import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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


@dataclass
class _ArtifactEntry:
    run_id: str
    run_created_at: str
    path: Path


class ArtifactsPage(Page):
    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Artifacts",
            subtitle="Browse briefs, RFCs, roadmaps, sprint plans, release checks, and PR summaries by run.",
        )
        self.engine = engine
        self._entries: list[_ArtifactEntry] = []
        self._run_order: dict[str, int] = {}

        controls = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        controls.addWidget(refresh)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search run id or artifact file...")
        self.search_input.textChanged.connect(self._apply_filters)
        controls.addWidget(self.search_input, stretch=2)

        self.run_filter = QComboBox()
        self.run_filter.currentIndexChanged.connect(self._apply_filters)
        controls.addWidget(self.run_filter, stretch=1)

        self.artifact_filter = QComboBox()
        self.artifact_filter.currentIndexChanged.connect(self._apply_filters)
        controls.addWidget(self.artifact_filter, stretch=1)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Run Newest", "run_desc")
        self.sort_combo.addItem("Run Oldest", "run_asc")
        self.sort_combo.addItem("Artifact A-Z", "artifact_asc")
        self.sort_combo.addItem("Artifact Z-A", "artifact_desc")
        self.sort_combo.currentIndexChanged.connect(self._apply_filters)
        controls.addWidget(self.sort_combo)

        self.compare_btn = QPushButton("Compare Previous")
        self.compare_btn.clicked.connect(self._compare_previous)
        controls.addWidget(self.compare_btn)

        self.open_btn = QPushButton("Open File")
        self.open_btn.clicked.connect(self._open_selected_file)
        controls.addWidget(self.open_btn)

        self.reveal_btn = QPushButton("Reveal Folder")
        self.reveal_btn.clicked.connect(self._reveal_selected_file)
        controls.addWidget(self.reveal_btn)

        self.export_btn = QPushButton("Export Copy")
        self.export_btn.clicked.connect(self._export_selected_copy)
        controls.addWidget(self.export_btn)

        self.clear_compare_btn = QPushButton("Clear Compare")
        self.clear_compare_btn.clicked.connect(self._show_selected)
        controls.addWidget(self.clear_compare_btn)
        controls.addStretch(1)
        self.body_layout.addLayout(controls)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("color: #8a90a2; font-size: 12px;")
        self.body_layout.addWidget(self.summary_label)

        self.compare_label = QLabel("")
        self.compare_label.setStyleSheet("color: #8a90a2; font-size: 12px;")
        self.body_layout.addWidget(self.compare_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Run / Artifact", "Updated"])
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
        selected_path = self._selected_artifact_path()
        self._entries = []
        self._run_order = {}
        self.compare_label.setText("")

        if self.engine.current_project() is None:
            self.tree.clear()
            self.summary_label.setText("")
            placeholder = QTreeWidgetItem(self.tree, ["Open a project to see artifacts"])
            placeholder.setDisabled(True)
            self._set_selection_action_enabled(False)
            return

        runs = self.engine.list_runs()
        for idx, run in enumerate(runs):
            run_id = run["id"]
            self._run_order[run_id] = idx
            for path in self.engine.list_artifacts(run_id):
                self._entries.append(
                    _ArtifactEntry(
                        run_id=run_id,
                        run_created_at=str(run.get("created_at", "")),
                        path=path,
                    )
                )

        self._update_filter_controls()
        self._apply_filters(selected_path=selected_path)

    def focus_artifact(self, run_id: str, path) -> None:
        self._refresh()
        self.search_input.clear()
        self.run_filter.setCurrentIndex(0)
        self.artifact_filter.setCurrentIndex(0)
        target = Path(path)
        self._apply_filters(selected_path=target)
        if self.tree.currentItem() is None:
            self.compare_label.setText(f"Artifact not visible after refresh: {run_id}/{target.name}")

    def _show_selected(self) -> None:
        self.compare_label.setText("")
        path = self._selected_artifact_path()
        self._set_selection_action_enabled(path is not None)
        if path is None:
            return
        self.viewer.show_path(path)

    def _compare_previous(self) -> None:
        current_path = self._selected_artifact_path()
        if current_path is None:
            QMessageBox.information(self, "Select artifact", "Select an artifact first.")
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

    def _update_filter_controls(self) -> None:
        selected_run = str(self.run_filter.currentData() or "__all__")
        selected_artifact = str(self.artifact_filter.currentData() or "__all__")

        run_ids = sorted({entry.run_id for entry in self._entries}, reverse=True)
        artifact_names = sorted({entry.path.stem for entry in self._entries})

        self.run_filter.blockSignals(True)
        self.run_filter.clear()
        self.run_filter.addItem("All Runs", "__all__")
        for run_id in run_ids:
            self.run_filter.addItem(run_id, run_id)
        self._restore_combo_selection(self.run_filter, selected_run)
        self.run_filter.blockSignals(False)

        self.artifact_filter.blockSignals(True)
        self.artifact_filter.clear()
        self.artifact_filter.addItem("All Artifacts", "__all__")
        for artifact in artifact_names:
            self.artifact_filter.addItem(artifact, artifact)
        self._restore_combo_selection(self.artifact_filter, selected_artifact)
        self.artifact_filter.blockSignals(False)

    def _apply_filters(self, _value=None, *, selected_path: Path | None = None) -> None:
        if self.engine.current_project() is None:
            return
        query = self.search_input.text().strip().lower()
        selected_run = str(self.run_filter.currentData() or "__all__")
        selected_artifact = str(self.artifact_filter.currentData() or "__all__")
        sort_mode = str(self.sort_combo.currentData() or "run_desc")

        filtered: list[_ArtifactEntry] = []
        for entry in self._entries:
            if query and query not in entry.run_id.lower() and query not in entry.path.name.lower():
                continue
            if selected_run != "__all__" and entry.run_id != selected_run:
                continue
            if selected_artifact != "__all__" and entry.path.stem != selected_artifact:
                continue
            filtered.append(entry)

        filtered = self._sort_entries(filtered, sort_mode=sort_mode)
        self._render_tree(filtered, selected_path=selected_path)

    def _sort_entries(
        self,
        entries: list[_ArtifactEntry],
        *,
        sort_mode: str,
    ) -> list[_ArtifactEntry]:
        if sort_mode == "run_asc":
            return sorted(entries, key=lambda e: (-self._run_order.get(e.run_id, 0), e.path.name.lower()))
        if sort_mode == "artifact_asc":
            return sorted(entries, key=lambda e: (e.path.name.lower(), self._run_order.get(e.run_id, 0)))
        if sort_mode == "artifact_desc":
            return sorted(
                entries,
                key=lambda e: (e.path.name.lower(), self._run_order.get(e.run_id, 0)),
                reverse=True,
            )
        return sorted(entries, key=lambda e: (self._run_order.get(e.run_id, 0), e.path.name.lower()))

    def _render_tree(self, entries: list[_ArtifactEntry], *, selected_path: Path | None) -> None:
        self.tree.clear()
        self.compare_label.setText("")
        if not entries:
            placeholder = QTreeWidgetItem(self.tree, ["No artifacts match current filters"])
            placeholder.setDisabled(True)
            self.summary_label.setText("0 artifacts shown")
            self._set_selection_action_enabled(False)
            return

        grouped: dict[str, list[_ArtifactEntry]] = defaultdict(list)
        for entry in entries:
            grouped[entry.run_id].append(entry)

        ordered_runs = sorted(grouped.keys(), key=lambda run_id: self._run_order.get(run_id, 0))
        for run_id in ordered_runs:
            run_entries = grouped[run_id]
            run_created = run_entries[0].run_created_at
            run_item = QTreeWidgetItem(self.tree, [run_id, run_created])
            run_item.setData(0, Qt.ItemDataRole.UserRole + 1, run_id)
            for entry in run_entries:
                child = QTreeWidgetItem(run_item, [entry.path.name, _fmt_mtime(entry.path)])
                child.setData(0, Qt.ItemDataRole.UserRole, entry.path)
                if selected_path is not None and str(entry.path) == str(selected_path):
                    self.tree.setCurrentItem(child)
            run_item.setExpanded(True)

        self.summary_label.setText(f"{len(entries)} artifacts shown across {len(grouped)} runs")
        if self.tree.currentItem() is None and self.tree.topLevelItemCount() > 0:
            first_run = self.tree.topLevelItem(0)
            if first_run.childCount() > 0:
                self.tree.setCurrentItem(first_run.child(0))
        self._set_selection_action_enabled(self._selected_artifact_path() is not None)

    def _selected_artifact_path(self) -> Path | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        path = item.data(0, Qt.ItemDataRole.UserRole)
        return path if isinstance(path, Path) else None

    def _set_selection_action_enabled(self, enabled: bool) -> None:
        self.compare_btn.setEnabled(enabled)
        self.clear_compare_btn.setEnabled(enabled)
        self.open_btn.setEnabled(enabled)
        self.reveal_btn.setEnabled(enabled)
        self.export_btn.setEnabled(enabled)

    def _open_selected_file(self) -> None:
        path = self._selected_artifact_path()
        if path is None:
            QMessageBox.information(self, "Select artifact", "Select an artifact first.")
            return
        try:
            _open_path_with_system(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Open file failed", str(exc))

    def _reveal_selected_file(self) -> None:
        path = self._selected_artifact_path()
        if path is None:
            QMessageBox.information(self, "Select artifact", "Select an artifact first.")
            return
        try:
            _open_path_with_system(path.parent)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Open folder failed", str(exc))

    def _export_selected_copy(self) -> None:
        path = self._selected_artifact_path()
        if path is None:
            QMessageBox.information(self, "Select artifact", "Select an artifact first.")
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Export Artifact Copy",
            str(path.name),
            "All Files (*.*)",
        )
        if not selected:
            return
        target = Path(selected)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", f"Could not export artifact:\n{exc}")
            return
        QMessageBox.information(self, "Export complete", f"Saved copy to:\n{target}")

    @staticmethod
    def _restore_combo_selection(combo: QComboBox, value: str) -> None:
        for idx in range(combo.count()):
            if str(combo.itemData(idx)) == value:
                combo.setCurrentIndex(idx)
                return
        combo.setCurrentIndex(0)


def _read_artifact_for_compare(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() != ".json":
        return text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


def _fmt_mtime(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
    except OSError:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _open_path_with_system(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
        return
    subprocess.run(["xdg-open", str(path)], check=False)
