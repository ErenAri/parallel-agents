from __future__ import annotations

from parallel_agents.desktop._qt import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService
from parallel_agents.desktop.widgets.worker_grid import WorkerGrid


class RunsPage(Page):
    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Runs",
            subtitle="Kick off a pipeline run and watch each specialist agent in real time.",
        )
        self.engine = engine

        task_row = QHBoxLayout()
        task_row.addWidget(QLabel("Task:"))
        self.task_input = QLineEdit()
        self.task_input.setPlaceholderText(
            "e.g. Review for security and quality issues"
        )
        task_row.addWidget(self.task_input, stretch=1)

        self.start_btn = QPushButton("Start Run")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self._start_run)
        task_row.addWidget(self.start_btn)
        self.body_layout.addLayout(task_row)

        self.worker_grid = WorkerGrid()
        self.body_layout.addWidget(self.worker_grid)

        self.body_layout.addWidget(QLabel("Activity"))
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setPlaceholderText("Run events will stream here.")
        self.body_layout.addWidget(self.activity, stretch=1)

    def _start_run(self) -> None:
        project = self.engine.current_project()
        if project is None:
            QMessageBox.warning(self, "No project", "Open a project first.")
            return
        task = self.task_input.text().strip()
        if not task:
            QMessageBox.warning(self, "Empty task", "Describe the task to run.")
            return

        self.activity.appendPlainText(f"[queued] {task}")
        for role in self.worker_grid.tiles:
            self.worker_grid.update_worker(role, "idle", "Waiting")

        # TODO: wire AsyncJob -> parallel_agents.Pipeline.run() and stream
        # progress events back to update_worker / activity.
        QMessageBox.information(
            self,
            "Not wired yet",
            "Pipeline execution will be connected next. The UI shell is in place.",
        )
