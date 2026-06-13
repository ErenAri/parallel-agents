from __future__ import annotations

from parallel_agents.desktop._qt import (
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    Signal,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService, WorkspaceHome
from parallel_agents.desktop.widgets.design_system import (
    ActionRow,
    Card,
    SectionHeader,
    StatCard,
    StatusLine,
)


class HomePage(Page):
    navigate_requested = Signal(str)
    open_project_requested = Signal()
    init_project_requested = Signal()
    run_requested = Signal(str)

    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Command Center",
            subtitle="Run your local AI software company from one calm, auditable cockpit.",
        )
        self.engine = engine

        hero = Card(hero=True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(22, 20, 22, 20)
        hero_layout.setSpacing(12)

        hero_layout.addWidget(
            SectionHeader(
                "What should the team do?",
                "Describe the outcome. Parallel Agents will plan, fan out specialist workers, merge results, and ask for approval before sensitive actions.",
            )
        )

        command_row = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setObjectName("CommandInput")
        self.command_input.setPlaceholderText(
            "Review this repo for launch blockers, security risks, and next actions"
        )
        self.command_input.returnPressed.connect(self._start_run)
        start_btn = QPushButton("Start Run")
        start_btn.setObjectName("Primary")
        start_btn.clicked.connect(self._start_run)
        command_row.addWidget(self.command_input, stretch=1)
        command_row.addWidget(start_btn)
        hero_layout.addLayout(command_row)

        hero_actions = ActionRow()
        hero_actions.add_action("Open Project", self.open_project_requested.emit)
        hero_actions.add_action("Initialize Office", self.init_project_requested.emit)
        hero_actions.add_action("Approvals", lambda: self.navigate_requested.emit("approvals"))
        hero_actions.add_action("Artifacts", lambda: self.navigate_requested.emit("artifacts"))
        hero_actions.add_stretch()
        hero_layout.addWidget(hero_actions)
        self.body_layout.addWidget(hero)

        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(12)
        self.run_stat = StatCard("Runs")
        self.artifact_stat = StatCard("Artifacts")
        self.approval_stat = StatCard("Approvals")
        self.health_stat = StatCard("Readiness")
        for index, card in enumerate(
            [self.run_stat, self.artifact_stat, self.approval_stat, self.health_stat]
        ):
            self.stats_grid.addWidget(card, 0, index)
        self.body_layout.addLayout(self.stats_grid)

        middle = QHBoxLayout()
        middle.setSpacing(12)

        self.status_card = Card()
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(18, 16, 18, 16)
        status_layout.setSpacing(10)
        status_layout.addWidget(SectionHeader("System Status"))
        self.project_status = StatusLine("Project", "idle", "No project open")
        self.gateway_status = StatusLine("Gateway", "idle", "Stopped")
        self.github_status = StatusLine("GitHub", "idle", "Run doctor from Projects")
        self.model_status = StatusLine("Models", "idle", "Deterministic until configured")
        status_layout.addWidget(self.project_status)
        status_layout.addWidget(self.gateway_status)
        status_layout.addWidget(self.github_status)
        status_layout.addWidget(self.model_status)
        middle.addWidget(self.status_card, stretch=1)

        self.runs_card = Card()
        runs_layout = QVBoxLayout(self.runs_card)
        runs_layout.setContentsMargins(18, 16, 18, 16)
        runs_layout.setSpacing(10)
        runs_header = QHBoxLayout()
        runs_header.addWidget(SectionHeader("Recent Runs"), stretch=1)
        view_runs = QPushButton("View All")
        view_runs.clicked.connect(lambda: self.navigate_requested.emit("runs"))
        runs_header.addWidget(view_runs)
        runs_layout.addLayout(runs_header)
        self.recent_runs = QListWidget()
        self.recent_runs.setMinimumHeight(150)
        runs_layout.addWidget(self.recent_runs)
        middle.addWidget(self.runs_card, stretch=1)

        self.body_layout.addLayout(middle, stretch=1)

        self.readiness_card = Card()
        readiness_layout = QVBoxLayout(self.readiness_card)
        readiness_layout.setContentsMargins(18, 16, 18, 16)
        readiness_layout.setSpacing(10)
        readiness_layout.addWidget(
            SectionHeader(
                "Readiness Checklist",
                "The desktop should make blockers obvious before agents spend time.",
            )
        )
        self.readiness_list = QListWidget()
        self.readiness_list.setMinimumHeight(120)
        readiness_layout.addWidget(self.readiness_list)
        self.body_layout.addWidget(self.readiness_card)

        self._refresh()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._refresh()

    def _start_run(self) -> None:
        task = self.command_input.text().strip()
        if not task:
            QMessageBox.information(
                self,
                "Describe the work",
                "Enter the outcome you want the agent team to produce.",
            )
            return
        self.run_requested.emit(task)

    def _refresh(self) -> None:
        project = self.engine.current_project()
        gateway = self.engine.gateway_status()
        if project is None:
            self._render_no_project(gateway.running)
            return

        try:
            home = self.engine.workspace_home()
        except Exception as exc:  # noqa: BLE001
            self.project_status.set_status("error", str(exc))
            return
        self._render_home(home, gateway.running)

    def _render_no_project(self, gateway_running: bool) -> None:
        self.run_stat.set_value("—", "Open a project to start")
        self.artifact_stat.set_value("—", "")
        self.approval_stat.set_value("—", "")
        self.health_stat.set_value("Setup", "Project required")
        self.project_status.set_status("idle", "Open or initialize a project")
        self.gateway_status.set_status(
            "done" if gateway_running else "idle",
            "Running" if gateway_running else "Stopped",
        )
        self.github_status.set_status("idle", "Open a project first")
        self.model_status.set_status("idle", "Configure in Settings")
        self.recent_runs.clear()
        self.recent_runs.addItem("No project open.")
        self.readiness_list.clear()
        self.readiness_list.addItem("1. Open a project folder")
        self.readiness_list.addItem("2. Run onboarding from Projects")
        self.readiness_list.addItem("3. Start a run from this command center")

    def _render_home(self, home: WorkspaceHome, gateway_running: bool) -> None:
        self.run_stat.set_value(str(home.run_count), f"Latest: {home.latest_run_id or 'none'}")
        self.artifact_stat.set_value(str(home.artifact_count), "Run-linked outputs")
        self.approval_stat.set_value(
            str(home.pending_approval_count),
            f"{home.approved_approval_count} approved · {home.rejected_approval_count} rejected",
        )
        health_value = "Ready" if home.diagnostics_healthy else "Check"
        health_hint = (
            f"{home.diagnostics_passed} passed · "
            f"{home.diagnostics_warnings} warnings · "
            f"{home.diagnostics_failures} failures"
        )
        self.health_stat.set_value(health_value, health_hint)

        branch = f" · {home.current_branch}" if home.current_branch else ""
        self.project_status.set_status(
            "done",
            f"{home.project_name}{branch} · {home.project_root}",
        )
        self.gateway_status.set_status(
            "done" if gateway_running else "idle",
            "Running" if gateway_running else "Stopped",
        )
        self.github_status.set_status(
            "done" if home.diagnostics_failures == 0 else "running",
            "No failed checks" if home.diagnostics_failures == 0 else "Review diagnostics",
        )
        self.model_status.set_status("idle", "Settings control deterministic vs LLM mode")

        self.recent_runs.clear()
        if not home.recent_runs:
            self.recent_runs.addItem("No runs yet. Start one from the command bar.")
        for run in home.recent_runs:
            created = str(run.get("created_at") or "")
            artifact_count = run.get("artifact_count", 0)
            self.recent_runs.addItem(
                f"{run.get('id')} · {artifact_count} artifacts · {created}"
            )

        self.readiness_list.clear()
        for check in home.diagnostics_checks[:8]:
            name = str(check.get("name", "check"))
            status = str(check.get("status", "unknown"))
            detail = str(check.get("detail", "") or check.get("description", ""))
            prefix = _status_prefix(status)
            self.readiness_list.addItem(f"{prefix} {name}: {status} {detail}".strip())
        if not home.diagnostics_checks:
            self.readiness_list.addItem("No diagnostics available.")


def _status_prefix(status: str) -> str:
    normalized = status.strip().lower()
    if normalized in {"passed", "ok", "success"}:
        return "✓"
    if normalized in {"warning", "warn"}:
        return "!"
    if normalized in {"failed", "error"}:
        return "×"
    return "•"
