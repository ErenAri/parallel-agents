from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from parallel_agents.desktop._qt import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    Qt,
    QVBoxLayout,
    QWidget,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService
from parallel_agents.desktop.services.workers import AsyncJob
from parallel_agents.desktop.widgets.artifact_viewer import ArtifactViewer
from parallel_agents.project_office import office_dir


class ApprovalsPage(Page):
    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Approvals",
            subtitle="Review pending writes before they touch GitHub or the repository.",
        )
        self.engine = engine
        self._job: AsyncJob | None = None

        refresh_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        refresh_row.addWidget(refresh_btn)
        refresh_row.addWidget(QLabel("Show:"))
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["Pending", "All", "Approved", "Rejected"])
        self.scope_combo.currentIndexChanged.connect(self._refresh)
        refresh_row.addWidget(self.scope_combo)
        refresh_row.addWidget(QLabel("Approver:"))
        self.approver_input = QLineEdit()
        self.approver_input.setPlaceholderText("your-name")
        self.approver_input.setMaximumWidth(220)
        refresh_row.addWidget(self.approver_input)
        self.bulk_approve_btn = QPushButton("Approve Visible")
        self.bulk_approve_btn.clicked.connect(self._approve_visible_pending)
        refresh_row.addWidget(self.bulk_approve_btn)
        self.bulk_reject_btn = QPushButton("Reject Visible")
        self.bulk_reject_btn.clicked.connect(self._reject_visible_pending)
        refresh_row.addWidget(self.bulk_reject_btn)
        refresh_row.addStretch(1)
        self.body_layout.addLayout(refresh_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.list = QListWidget()
        self.list.setSelectionMode(self.list.SelectionMode.ExtendedSelection)
        self.list.itemSelectionChanged.connect(self._show_selected)
        splitter.addWidget(self.list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.viewer = ArtifactViewer()
        right_layout.addWidget(self.viewer, stretch=2)

        preview_row = QHBoxLayout()
        self.preview_btn = QPushButton("Preview Artifact")
        self.preview_btn.clicked.connect(self._preview_selected_artifact)
        preview_row.addWidget(self.preview_btn)
        self.diff_btn = QPushButton("Diff Previous")
        self.diff_btn.clicked.connect(self._diff_selected_artifact)
        preview_row.addWidget(self.diff_btn)
        preview_row.addStretch(1)
        right_layout.addLayout(preview_row)

        self.compare_label = QLabel("")
        self.compare_label.setStyleSheet("color: #8a90a2; font-size: 12px;")
        right_layout.addWidget(self.compare_label)

        right_layout.addWidget(QLabel("Related Audit Events"))
        self.audit_list = QListWidget()
        self.audit_list.itemSelectionChanged.connect(self._show_selected_audit_event)
        right_layout.addWidget(self.audit_list, stretch=1)

        action_row = QHBoxLayout()
        self.approve_btn = QPushButton("Approve Selected")
        self.approve_btn.setObjectName("Primary")
        self.approve_btn.clicked.connect(self._approve_selected)
        self.reject_btn = QPushButton("Reject Selected")
        self.reject_btn.setObjectName("Danger")
        self.reject_btn.clicked.connect(self._reject_selected)
        self.apply_btn = QPushButton("Apply Plan")
        self.apply_btn.clicked.connect(self._apply_selected_plan)
        self.apply_btn.setEnabled(False)
        action_row.addStretch(1)
        action_row.addWidget(self.apply_btn)
        action_row.addWidget(self.reject_btn)
        action_row.addWidget(self.approve_btn)
        right_layout.addLayout(action_row)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        self.body_layout.addWidget(splitter, stretch=1)

        self._refresh()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        self.list.clear()
        self.audit_list.clear()
        self.compare_label.setText("")
        if self.engine.current_project() is None:
            item = QListWidgetItem("Open a project to see approvals")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.list.addItem(item)
            self._show_selected()
            return

        selected = self.scope_combo.currentText().strip().lower()
        if selected == "pending":
            approvals = self.engine.list_pending_approvals()
            empty_label = "No pending approvals"
        else:
            approvals = self.engine.list_all_approvals()
            if selected == "approved":
                approvals = [
                    entry
                    for entry in approvals
                    if str(entry.get("data", {}).get("status", "")).lower() == "approved"
                ]
                empty_label = "No approved approvals"
            elif selected == "rejected":
                approvals = [
                    entry
                    for entry in approvals
                    if str(entry.get("data", {}).get("status", "")).lower() == "rejected"
                ]
                empty_label = "No rejected approvals"
            else:
                empty_label = "No approvals found"

        if not approvals:
            item = QListWidgetItem(empty_label)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.list.addItem(item)
            self._show_selected()
            return

        for entry in approvals:
            data = entry["data"]
            path = entry["path"]
            label = data.get("title") or data.get("run_id") or path.name
            status = str(data.get("status", "pending"))
            item = QListWidgetItem(f"{label}  -  {data.get('artifact', '?')}  -  {status}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list.addItem(item)
        if self.list.count() > 0:
            self.list.setCurrentRow(0)
        self._show_selected()

    def _selected_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for item in self.list.selectedItems():
            payload = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, dict):
                entries.append(payload)
        return entries

    def _selected_entry(self) -> dict[str, Any] | None:
        item = self.list.currentItem()
        if item is None:
            return None
        payload = item.data(Qt.ItemDataRole.UserRole)
        return payload if isinstance(payload, dict) else None

    def _approval_entries_in_list(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for idx in range(self.list.count()):
            item = self.list.item(idx)
            payload = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, dict):
                entries.append(payload)
        return entries

    def _show_selected(self) -> None:
        entry = self._selected_entry()
        selected_entries = self._selected_entries()
        has_pending_selection = any(
            str(e.get("data", {}).get("status", "")).lower() == "pending"
            for e in selected_entries
        )

        self.bulk_approve_btn.setEnabled(bool(self._visible_pending_entries()))
        self.bulk_reject_btn.setEnabled(bool(self._visible_pending_entries()))
        self.approve_btn.setEnabled(has_pending_selection)
        self.reject_btn.setEnabled(has_pending_selection)
        self.preview_btn.setEnabled(entry is not None)
        self.diff_btn.setEnabled(entry is not None)

        if entry is None:
            self.apply_btn.setEnabled(False)
            self.audit_list.clear()
            return

        data = entry["data"]
        display = dict(data)
        artifact_path = self._artifact_path_for_entry(entry)
        display["approval_file"] = str(entry["path"])
        display["resolved_artifact_path"] = str(artifact_path) if artifact_path else None
        self.viewer.show_data(display)

        status = str(data.get("status", "pending")).lower()
        can_apply = (
            status == "approved"
            and str(data.get("artifact", "")) == "issue-plan"
            and bool(data.get("run_id"))
        )
        self.apply_btn.setEnabled(can_apply)
        self._load_audit_events(entry)

    def _load_audit_events(self, entry: dict[str, Any]) -> None:
        self.audit_list.clear()
        data = entry.get("data", {})
        run_id = str(data.get("run_id", "")).strip() or None
        approval_id = str(data.get("approval_id", "")).strip() or None
        if run_id is None and approval_id is None:
            return
        events = self.engine.list_audit_events(run_id=run_id, approval_id=approval_id, limit=200)
        if not events:
            self.audit_list.addItem("No related audit events")
            return
        for payload in reversed(events):
            label = (
                f"{payload.get('timestamp', '-')}  "
                f"{payload.get('event', '-')}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, payload)
            self.audit_list.addItem(item)

    def _show_selected_audit_event(self) -> None:
        item = self.audit_list.currentItem()
        if item is None:
            return
        payload = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(payload, dict):
            self.viewer.show_data(payload)

    def _approver(self) -> str:
        return self.approver_input.text().strip() or "unknown"

    def _visible_pending_entries(self) -> list[dict[str, Any]]:
        return [
            entry
            for entry in self._approval_entries_in_list()
            if str(entry.get("data", {}).get("status", "")).lower() == "pending"
        ]

    def _approve_visible_pending(self) -> None:
        from parallel_agents.desktop.widgets.error_dialog import show_error

        entries = self._visible_pending_entries()
        if not entries:
            QMessageBox.information(self, "No pending approvals", "No pending approvals in current view.")
            return
        note, ok = QInputDialog.getText(self, "Bulk Approve", "Approval note (optional):")
        if not ok:
            return
        confirm = QMessageBox.question(
            self,
            "Confirm bulk approve",
            f"Approve {len(entries)} pending approvals?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        failures: list[str] = []
        for entry in entries:
            try:
                self.engine.approve(entry["path"], approver=self._approver(), note=note)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{entry['path']}: {exc}")
        if failures:
            show_error(
                self,
                "Bulk approve partially failed",
                f"{len(failures)} approvals failed.",
                details="\n".join(failures),
            )
        self._refresh()

    def _reject_visible_pending(self) -> None:
        from parallel_agents.desktop.widgets.error_dialog import show_error

        entries = self._visible_pending_entries()
        if not entries:
            QMessageBox.information(self, "No pending approvals", "No pending approvals in current view.")
            return
        reason, ok = QInputDialog.getText(self, "Bulk Reject", "Rejection reason:")
        if not ok:
            return
        confirm = QMessageBox.question(
            self,
            "Confirm bulk reject",
            f"Reject {len(entries)} pending approvals?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        failures: list[str] = []
        for entry in entries:
            try:
                self.engine.reject(entry["path"], approver=self._approver(), reason=reason)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{entry['path']}: {exc}")
        if failures:
            show_error(
                self,
                "Bulk reject partially failed",
                f"{len(failures)} approvals failed.",
                details="\n".join(failures),
            )
        self._refresh()

    def _approve_selected(self) -> None:
        from parallel_agents.desktop.widgets.error_dialog import show_error

        entries = [
            entry
            for entry in self._selected_entries()
            if str(entry.get("data", {}).get("status", "")).lower() == "pending"
        ]
        if not entries:
            QMessageBox.information(self, "No pending selection", "Select at least one pending approval first.")
            return
        note, ok = QInputDialog.getText(self, "Approve selected", "Approval note (optional):")
        if not ok:
            return
        failures: list[str] = []
        for entry in entries:
            try:
                self.engine.approve(entry["path"], approver=self._approver(), note=note)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{entry['path']}: {exc}")
        if failures:
            show_error(
                self,
                "Approve selected partially failed",
                f"{len(failures)} approvals failed.",
                details="\n".join(failures),
            )
        self._refresh()

    def _reject_selected(self) -> None:
        from parallel_agents.desktop.widgets.error_dialog import show_error

        entries = [
            entry
            for entry in self._selected_entries()
            if str(entry.get("data", {}).get("status", "")).lower() == "pending"
        ]
        if not entries:
            QMessageBox.information(self, "No pending selection", "Select at least one pending approval first.")
            return
        reason, ok = QInputDialog.getText(self, "Reject selected", "Reason:")
        if not ok:
            return
        failures: list[str] = []
        for entry in entries:
            try:
                self.engine.reject(entry["path"], approver=self._approver(), reason=reason)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{entry['path']}: {exc}")
        if failures:
            show_error(
                self,
                "Reject selected partially failed",
                f"{len(failures)} approvals failed.",
                details="\n".join(failures),
            )
        self._refresh()

    def _preview_selected_artifact(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(self, "No selection", "Select an approval first.")
            return
        artifact_path = self._artifact_path_for_entry(entry)
        if artifact_path is None or not artifact_path.exists():
            QMessageBox.information(self, "Artifact missing", "Could not resolve artifact file for this approval.")
            return
        self.viewer.show_path(artifact_path)
        self.compare_label.setText(f"Previewing: {artifact_path.name}")

    def _diff_selected_artifact(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(self, "No selection", "Select an approval first.")
            return
        current_path = self._artifact_path_for_entry(entry)
        if current_path is None or not current_path.exists():
            QMessageBox.information(self, "Artifact missing", "Could not resolve artifact file for this approval.")
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

    def _artifact_path_for_entry(self, entry: dict[str, Any]) -> Path | None:
        data = entry.get("data", {})
        run_id = str(data.get("run_id", "")).strip()
        artifact_name = str(data.get("artifact", "")).strip()
        relpath = str(data.get("artifact_path", "")).strip()

        if self.engine.current_project() is None:
            return None
        project_root = self.engine.require_project()
        base = office_dir(project_root)

        if relpath:
            candidate = base / relpath
            if candidate.exists():
                return candidate
        if run_id and artifact_name:
            direct = base / run_id / "company" / f"{artifact_name}.json"
            if direct.exists():
                return direct
            for path in self.engine.list_artifacts(run_id):
                if path.stem == artifact_name:
                    return path
        return None

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

    def _apply_selected_plan(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(
                self, "No selection", "Select an approved issue-plan entry."
            )
            return
        data = entry["data"]
        if str(data.get("status", "")).lower() != "approved":
            QMessageBox.warning(
                self, "Not approved", "Only approved issue-plan entries can be applied."
            )
            return
        run_id = str(data.get("run_id", "")).strip()
        if not run_id:
            QMessageBox.warning(self, "Missing run", "Selected approval has no run_id.")
            return

        if self._job is not None and self._job.isRunning():
            QMessageBox.information(
                self, "Apply running", "An apply is already running. Wait for it to finish."
            )
            return

        mode_choice = QMessageBox.question(
            self,
            "Apply plan",
            "Apply issue plan to GitHub now?\nChoose Yes for live apply, No for dry-run.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No,
        )
        if mode_choice == QMessageBox.StandardButton.Cancel:
            return
        dry_run = mode_choice != QMessageBox.StandardButton.Yes

        self.apply_btn.setEnabled(False)
        self.apply_btn.setText("Applying...")
        self._job = AsyncJob(
            lambda: self.engine.apply_issue_plan_async(run_id, dry_run=dry_run)
        )
        self._job.finished_ok.connect(self._on_apply_finished)
        self._job.failed.connect(self._on_apply_failed)
        self._job.start()

    def _on_apply_finished(self, result) -> None:
        self.apply_btn.setText("Apply Plan")
        mode = str(result.get("mode", "dry-run"))
        created = sum(1 for issue in result.get("issues", []) if issue.get("created"))
        planned = int(result.get("issues_planned", 0) or 0)
        QMessageBox.information(
            self,
            "Apply complete",
            f"Mode: {mode}\nCreated issues: {created}/{planned}",
        )
        self._refresh()

    def _on_apply_failed(self, error: str) -> None:
        from parallel_agents.desktop.widgets.error_dialog import show_error

        self.apply_btn.setText("Apply Plan")
        self.apply_btn.setEnabled(True)
        show_error(
            self,
            "Apply failed",
            "The GitHub apply could not complete. See details for the full error.",
            details=error,
        )


def _read_artifact_for_compare(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() != ".json":
        return text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
