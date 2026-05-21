from __future__ import annotations

from parallel_agents.desktop._qt import (
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
        action_row.addStretch(1)
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
        for entry in self.engine.list_pending_approvals():
            data = entry["data"]
            path = entry["path"]
            label = data.get("title") or data.get("run_id") or path.name
            item = QListWidgetItem(f"{label}  ·  {data.get('artifact', '?')}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list.addItem(item)

    def _selected_entry(self) -> dict | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _show_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        self.viewer.show_data(entry["data"])

    def _approver(self) -> str:
        return self.approver_input.text().strip() or "unknown"

    def _approve(self) -> None:
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
            QMessageBox.critical(self, "Approve failed", str(exc))
            return
        self._refresh()

    def _reject(self) -> None:
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
            QMessageBox.critical(self, "Reject failed", str(exc))
            return
        self._refresh()
