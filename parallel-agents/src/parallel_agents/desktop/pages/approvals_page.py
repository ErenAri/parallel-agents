from __future__ import annotations

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
from parallel_agents.desktop.widgets.artifact_viewer import ArtifactViewer


class ApprovalsPage(Page):
    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Approvals",
            subtitle="Review pending writes before they touch GitHub or the repository.",
        )
        self.engine = engine

        refresh_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        refresh_row.addWidget(refresh_btn)
        refresh_row.addWidget(QLabel("Show:"))
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["Pending", "All", "Approved", "Rejected"])
        self.scope_combo.currentIndexChanged.connect(self._refresh)
        refresh_row.addWidget(self.scope_combo)
        refresh_row.addStretch(1)
        refresh_row.addWidget(QLabel("Approver:"))
        self.approver_input = QLineEdit()
        self.approver_input.setPlaceholderText("your-name")
        self.approver_input.setMaximumWidth(220)
        refresh_row.addWidget(self.approver_input)
        self.body_layout.addLayout(refresh_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._show_selected)
        splitter.addWidget(self.list)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.viewer = ArtifactViewer()
        right_layout.addWidget(self.viewer, stretch=1)

        action_row = QHBoxLayout()
        self.approve_btn = QPushButton("Approve")
        self.approve_btn.setObjectName("Primary")
        self.approve_btn.clicked.connect(self._approve)
        self.reject_btn = QPushButton("Reject")
        self.reject_btn.setObjectName("Danger")
        self.reject_btn.clicked.connect(self._reject)
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
        self._show_selected()

    def _selected_entry(self) -> dict | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _show_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            self.approve_btn.setEnabled(False)
            self.reject_btn.setEnabled(False)
            self.apply_btn.setEnabled(False)
            return
        data = entry["data"]
        self.viewer.show_data(data)
        status = str(data.get("status", "pending")).lower()
        self.approve_btn.setEnabled(status == "pending")
        self.reject_btn.setEnabled(status == "pending")
        can_apply = (
            status == "approved"
            and str(data.get("artifact", "")) == "issue-plan"
            and bool(data.get("run_id"))
        )
        self.apply_btn.setEnabled(can_apply)

    def _approver(self) -> str:
        return self.approver_input.text().strip() or "unknown"

    def _approve(self) -> None:
        from parallel_agents.desktop.widgets.error_dialog import show_error

        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(self, "No selection", "Select a pending approval first.")
            return
        note, ok = QInputDialog.getText(self, "Approve", "Approval note (optional):")
        if not ok:
            return
        try:
            self.engine.approve(entry["path"], approver=self._approver(), note=note)
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Approve failed", str(exc), details=repr(exc))
            return
        self._refresh()

    def _reject(self) -> None:
        from parallel_agents.desktop.widgets.error_dialog import show_error

        entry = self._selected_entry()
        if entry is None:
            QMessageBox.information(self, "No selection", "Select a pending approval first.")
            return
        reason, ok = QInputDialog.getText(self, "Reject", "Reason:")
        if not ok:
            return
        try:
            self.engine.reject(entry["path"], approver=self._approver(), reason=reason)
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Reject failed", str(exc), details=repr(exc))
            return
        self._refresh()

    def _apply_selected_plan(self) -> None:
        from parallel_agents.desktop.widgets.error_dialog import show_error

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
        try:
            result = self.engine.apply_issue_plan(run_id, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Apply failed", str(exc), details=repr(exc))
            return

        mode = str(result.get("mode", "dry-run"))
        created = sum(1 for issue in result.get("issues", []) if issue.get("created"))
        planned = int(result.get("issues_planned", 0) or 0)
        QMessageBox.information(
            self,
            "Apply complete",
            f"Mode: {mode}\nCreated issues: {created}/{planned}",
        )
        self._refresh()
