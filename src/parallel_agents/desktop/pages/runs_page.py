from __future__ import annotations

from parallel_agents.desktop._qt import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    Signal,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService
from parallel_agents.desktop.services.workers import AsyncJob
from parallel_agents.desktop.widgets.design_system import Card, SectionHeader, StatCard, StatusLine
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
        self._event_status_seen = False

        hero = Card(hero=True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        hero_layout.setSpacing(12)
        hero_layout.addWidget(
            SectionHeader(
                "Start a specialist run",
                "Enter a clear outcome. The planner splits the work, specialists execute in parallel, and the judge writes the final result.",
            )
        )

        task_row = QHBoxLayout()
        self.task_input = QLineEdit()
        self.task_input.setObjectName("CommandInput")
        self.task_input.setPlaceholderText(
            "e.g. Review for security and quality issues"
        )
        task_row.addWidget(self.task_input, stretch=1)

        self.start_btn = QPushButton("Start Run")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self._start_run)
        task_row.addWidget(self.start_btn)
        hero_layout.addLayout(task_row)
        self.body_layout.addWidget(hero)

        stats_grid = QGridLayout()
        stats_grid.setSpacing(12)
        self.state_stat = StatCard("State", "Idle", "Waiting for a task")
        self.worker_stat = StatCard("Workers", "0", "No active workers")
        self.token_stat = StatCard("Tokens", "0", "Available after completion")
        self.cost_stat = StatCard("Cost", "$0.0000", "Available after completion")
        for index, card in enumerate(
            [self.state_stat, self.worker_stat, self.token_stat, self.cost_stat]
        ):
            stats_grid.addWidget(card, 0, index)
        self.body_layout.addLayout(stats_grid)

        status_card = Card()
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(18, 16, 18, 16)
        status_layout.setSpacing(8)
        status_layout.addWidget(SectionHeader("Run Status"))
        self.run_status = StatusLine("Pipeline", "idle", "Waiting for task")
        self.current_task_label = QLabel("No task queued.")
        self.current_task_label.setObjectName("CardMeta")
        self.current_task_label.setWordWrap(True)
        status_layout.addWidget(self.run_status)
        status_layout.addWidget(self.current_task_label)
        self.body_layout.addWidget(status_card)

        self.body_layout.addWidget(SectionHeader("Specialist Workers"))
        self.worker_grid = WorkerGrid()
        self.body_layout.addWidget(self.worker_grid)

        self.body_layout.addWidget(SectionHeader("Activity Log"))
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setPlaceholderText("Run events will stream here.")
        self.body_layout.addWidget(self.activity, stretch=1)

    def set_task(self, task: str, *, start: bool = False) -> None:
        self.task_input.setText(task.strip())
        self.task_input.setFocus()
        if start:
            self._start_run()

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

        self.activity.clear()
        self.activity.appendPlainText(f"[queued] {task}")
        for role in self.worker_grid.tiles:
            self.worker_grid.update_worker(role, "idle", "Waiting")
        self._active_workers.clear()
        self._event_status_seen = False
        self.start_btn.setEnabled(False)
        self.state_stat.set_value("Running", "Pipeline active")
        self.worker_stat.set_value("0", "Planner starting")
        self.token_stat.set_value("0", "Available after completion")
        self.cost_stat.set_value("$0.0000", "Available after completion")
        self.run_status.set_status("running", "Queued and starting")
        self.current_task_label.setText(task)

        async def _job():
            def _on_status(message: str) -> None:
                if self._job is not None:
                    self._job.progress.emit({"message": message})

            def _on_event(event: dict) -> None:
                if self._job is not None:
                    self._job.progress.emit({"event": event})

            return await self.engine.run_pipeline(
                task,
                on_status=_on_status,
                on_event=_on_event,
            )

        self._job = AsyncJob(_job)
        self._job.progress.connect(self._on_progress)
        self._job.finished_ok.connect(self._on_finished)
        self._job.failed.connect(self._on_failed)
        self._job.start()

    def _on_progress(self, payload: dict) -> None:
        event = payload.get("event")
        if isinstance(event, dict):
            self._event_status_seen = True
            self._apply_worker_status_from_event(event)
            self._update_run_status_from_event(event)
            return

        message = str(payload.get("message", "")).strip()
        if not message:
            return
        self.activity.appendPlainText(message)
        self.run_status.set_status("running", message[:180])
        if not self._event_status_seen:
            self._apply_worker_status_from_message(message)
            self.worker_stat.set_value(str(len(self._active_workers)), "Active workers")

    def _on_finished(self, result) -> None:
        self.start_btn.setEnabled(True)
        self._active_workers.clear()
        self.activity.appendPlainText(
            f"[done] run={result.run_id} tokens={result.total_tokens} cost=${result.total_cost_usd:.4f}"
        )
        self.state_stat.set_value("Done", f"Run {result.run_id}")
        self.worker_stat.set_value(str(len(result.worker_statuses)), "Completed workers")
        self.token_stat.set_value(str(result.total_tokens), "Total tokens")
        self.cost_stat.set_value(f"${result.total_cost_usd:.4f}", "Total cost")
        self.run_status.set_status("done", f"Final output saved for {result.run_id}")
        for role, status in result.worker_statuses.items():
            mapped = "done" if str(status).lower() not in {"error", "failed"} else "error"
            self.worker_grid.update_worker(role, mapped, f"Result: {status}")
        self.worker_grid.update_worker("judge", "done", "Final output saved")
        self.run_completed.emit(result.run_id)

    def _on_failed(self, error: str) -> None:
        from parallel_agents.desktop.widgets.error_dialog import show_error

        self.start_btn.setEnabled(True)
        self.activity.appendPlainText(f"[failed] {error}")
        self.state_stat.set_value("Failed", "Review details")
        self.run_status.set_status("error", error[:180])
        show_error(
            self,
            "Run failed",
            "Pipeline run could not complete. See details for the full error.",
            details=error,
        )

    def _update_run_status_from_event(self, event: dict) -> None:
        agent = str(event.get("agent") or "").strip()
        phase = str(event.get("phase") or "").strip()
        status = str(event.get("status") or "").strip()
        event_name = str(event.get("event") or "").strip()

        if agent == "pipeline":
            if phase == "planning":
                detail = "Planning" if status == "started" else "Plan completed"
                self.run_status.set_status("running", detail)
            elif phase == "splitting":
                self.run_status.set_status("running", "Preparing worker batches")
            elif phase == "execution":
                if status == "started":
                    self.run_status.set_status("running", "Specialists executing")
                elif status == "completed":
                    self.run_status.set_status("running", "Specialists completed")
            elif phase == "judging":
                detail = "Merging specialist outputs" if status == "started" else "Final output saved"
                self.run_status.set_status("running", detail)
        elif event_name == "worker_started":
            self.run_status.set_status("running", f"{agent} started")
        elif event_name == "worker_completed":
            self.run_status.set_status("running", f"{agent} completed")

        active_count = len(self._active_workers)
        self.worker_stat.set_value(str(active_count), "Active workers")

    def _apply_worker_status_from_event(self, event: dict) -> None:
        agent = str(event.get("agent") or "").strip()
        phase = str(event.get("phase") or "").strip()
        status = str(event.get("status") or "").strip()
        event_name = str(event.get("event") or "").strip()

        if agent == "pipeline":
            if phase == "planning":
                if status == "started":
                    self.worker_grid.update_worker("planner", "running", "Planning")
                elif status == "completed":
                    subtask_count = event.get("subtask_count")
                    detail = (
                        f"Plan completed ({subtask_count} subtasks)"
                        if subtask_count is not None
                        else "Plan completed"
                    )
                    self.worker_grid.update_worker("planner", "done", detail)
                return
            if phase == "splitting" and status == "completed":
                batch_count = event.get("batch_count")
                detail = (
                    f"Batches prepared ({batch_count})"
                    if batch_count is not None
                    else "Batches prepared"
                )
                self.worker_grid.update_worker("splitter", "done", detail)
                return
            if phase == "execution":
                if status == "started":
                    self.worker_grid.update_worker("splitter", "done", "Execution started")
                    self._active_workers.clear()
                    for role in _event_workers(event):
                        if role in self.worker_grid.tiles:
                            self.worker_grid.update_worker(role, "running", "Executing subtask")
                            self._active_workers.add(role)
                elif status == "completed":
                    results = event.get("results") if isinstance(event.get("results"), dict) else {}
                    for role, result_status in results.items():
                        mapped = _worker_grid_status(str(result_status))
                        self.worker_grid.update_worker(role, mapped, f"Result: {result_status}")
                        self._active_workers.discard(str(role))
                return
            if phase == "judging":
                if status == "started":
                    for role in list(self._active_workers):
                        if role in self.worker_grid.tiles:
                            self.worker_grid.update_worker(role, "done", "Subtask complete")
                    self._active_workers.clear()
                    self.worker_grid.update_worker("judge", "running", "Merging results")
                elif status == "completed":
                    self.worker_grid.update_worker("judge", "done", "Final output saved")
                return

        if agent in self.worker_grid.tiles:
            if event_name == "worker_started":
                self.worker_grid.update_worker(agent, "running", "Executing subtask")
                self._active_workers.add(agent)
                return
            if event_name == "worker_completed":
                mapped = _worker_grid_status(status)
                self.worker_grid.update_worker(agent, mapped, f"Result: {status or 'done'}")
                self._active_workers.discard(agent)
                return
            if status:
                mapped = _worker_grid_status(status)
                findings = event.get("findings")
                recommendations = event.get("recommendations")
                detail = f"Result: {status}"
                if findings is not None and recommendations is not None:
                    detail = f"{status}: {findings} findings, {recommendations} recommendations"
                self.worker_grid.update_worker(agent, mapped, detail)

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


def _event_workers(event: dict) -> list[str]:
    workers = event.get("workers")
    if isinstance(workers, list):
        return [str(item) for item in workers if str(item).strip()]
    return []


def _worker_grid_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {"error", "failed", "runtime_error", "parse_error", "worker_error"}:
        return "error"
    if normalized in {"started", "running"}:
        return "running"
    return "done"
