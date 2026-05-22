from __future__ import annotations

from parallel_agents.desktop._qt import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    Signal,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService
from parallel_agents.desktop.services.workers import AsyncJob
from parallel_agents.desktop.widgets.worker_grid import WorkerGrid


class RunsPage(Page):
    run_completed = Signal(str)  # run_id

    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Runs",
            subtitle="Kick off a pipeline run and watch each specialist agent in real time.",
        )
        self.engine = engine
        self._job: AsyncJob | None = None
        self._active_workers: set[str] = set()

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
        if self._job is not None and self._job.isRunning():
            QMessageBox.information(self, "Run in progress", "Wait for the current run to finish.")
            return
        task = self.task_input.text().strip()
        if not task:
            QMessageBox.warning(self, "Empty task", "Describe the task to run.")
            return

        self.activity.appendPlainText(f"[queued] {task}")
        for role in self.worker_grid.tiles:
            self.worker_grid.update_worker(role, "idle", "Waiting")
        self._active_workers.clear()
        self.start_btn.setEnabled(False)

        async def _job():
            def _on_status(message: str) -> None:
                if self._job is not None:
                    self._job.progress.emit({"message": message})

            return await self.engine.run_pipeline(task, on_status=_on_status)

        self._job = AsyncJob(_job)
        self._job.progress.connect(self._on_progress)
        self._job.finished_ok.connect(self._on_finished)
        self._job.failed.connect(self._on_failed)
        self._job.start()

    def _on_progress(self, payload: dict) -> None:
        message = str(payload.get("message", "")).strip()
        if not message:
            return
        self.activity.appendPlainText(message)
        self._apply_worker_status_from_message(message)

    def _on_finished(self, result) -> None:
        self.start_btn.setEnabled(True)
        self._active_workers.clear()
        self.activity.appendPlainText(
            f"[done] run={result.run_id} tokens={result.total_tokens} cost=${result.total_cost_usd:.4f}"
        )
        for role, status in result.worker_statuses.items():
            mapped = "done" if str(status).lower() not in {"error", "failed"} else "error"
            self.worker_grid.update_worker(role, mapped, f"Result: {status}")
        self.worker_grid.update_worker("judge", "done", "Final output saved")
        self.run_completed.emit(result.run_id)

    def _on_failed(self, error: str) -> None:
        from parallel_agents.desktop.widgets.error_dialog import show_error

        self.start_btn.setEnabled(True)
        self.activity.appendPlainText(f"[failed] {error}")
        show_error(
            self,
            "Run failed",
            "Pipeline run could not complete. See details for the full error.",
            details=error,
        )

    def _apply_worker_status_from_message(self, message: str) -> None:
        normalized = message.strip()
        if normalized.startswith("Planning:"):
            self.worker_grid.update_worker("planner", "running", normalized)
            return
        if normalized.startswith("Splitting tasks"):
            self.worker_grid.update_worker("planner", "done", "Plan completed")
            self.worker_grid.update_worker("splitter", "running", normalized)
            return
        if normalized.startswith("Executing "):
            self.worker_grid.update_worker("splitter", "done", "Batches prepared")
            return
        if normalized.startswith("Batch ") or normalized.startswith("Batch"):
            for role in list(self._active_workers):
                if role in self.worker_grid.tiles:
                    self.worker_grid.update_worker(role, "done", "Batch complete")
            self._active_workers.clear()

            workers_segment = normalized.split(":", maxsplit=1)
            if len(workers_segment) < 2:
                return
            workers_raw = workers_segment[1].strip().strip("[]")
            workers = [
                item.strip().strip("'").strip('"')
                for item in workers_raw.split(",")
                if item.strip()
            ]
            for role in workers:
                if role in self.worker_grid.tiles:
                    self.worker_grid.update_worker(role, "running", "Executing subtask")
                    self._active_workers.add(role)
            return
        if normalized.startswith("Judge is"):
            for role in list(self._active_workers):
                if role in self.worker_grid.tiles:
                    self.worker_grid.update_worker(role, "done", "Subtask complete")
            self._active_workers.clear()
            self.worker_grid.update_worker("judge", "running", normalized)
            return
        if normalized.startswith("Done. Run ID:"):
            self.worker_grid.update_worker("judge", "done", "Final merge complete")
