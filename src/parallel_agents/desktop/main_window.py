from __future__ import annotations

from parallel_agents.desktop._qt import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QThread,
    QVBoxLayout,
    QWidget,
)
from parallel_agents.desktop.pages.approvals_page import ApprovalsPage
from parallel_agents.desktop.pages.artifacts_page import ArtifactsPage
from parallel_agents.desktop.pages.company_page import CompanyPage
from parallel_agents.desktop.pages.home_page import HomePage
from parallel_agents.desktop.pages.projects_page import ProjectsPage
from parallel_agents.desktop.pages.runs_page import RunsPage
from parallel_agents.desktop.pages.settings_page import SettingsPage
from parallel_agents.desktop.services.engine import EngineService
from parallel_agents.desktop.widgets.app_chrome import TopBar
from parallel_agents.desktop.widgets.sidebar import Sidebar
from parallel_agents.desktop.widgets.status_bar import (
    llm_indicator_text,
    make_llm_label,
    make_project_label,
    make_run_label,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Parallel Agents Office")

        # Headless/smoke mode: skip the interactive "jobs still running" close
        # confirmation (a modal dialog has no one to dismiss it offscreen).
        self._headless = False

        self.engine = EngineService()
        # Apply persisted user-level settings on launch (project ones load on open).
        self.engine.settings_store().load()

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(
            sections=[
                ("Home", "home"),
                ("Projects", "projects"),
                ("Company", "company"),
                ("Runs", "runs"),
                ("Approvals", "approvals"),
                ("Artifacts", "artifacts"),
                ("Settings", "settings"),
            ]
        )
        self.sidebar.section_selected.connect(self._on_section_selected)

        self.stack = QStackedWidget()
        home_page = HomePage(self.engine)
        company_page = CompanyPage(self.engine)
        artifacts_page = ArtifactsPage(self.engine)
        projects_page = ProjectsPage(self.engine)
        runs_page = RunsPage(self.engine)

        company_page.artifact_created.connect(
            lambda run_id, path: self._jump_to_artifact(run_id, path)
        )
        company_page.artifact_created.connect(
            lambda run_id, _path: self._update_status_run(run_id)
        )
        projects_page.project_opened.connect(self._update_status_project)
        runs_page.run_completed.connect(self._update_status_run)
        home_page.navigate_requested.connect(self.sidebar.select)
        home_page.open_project_requested.connect(self._open_project_from_home)
        home_page.init_project_requested.connect(self._init_project_from_home)
        home_page.run_requested.connect(self._start_run_from_home)

        self.pages: dict[str, QWidget] = {
            "home": home_page,
            "projects": projects_page,
            "company": company_page,
            "runs": runs_page,
            "approvals": ApprovalsPage(self.engine),
            "artifacts": artifacts_page,
            "settings": SettingsPage(self.engine),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.top_bar = TopBar()
        self.top_bar.run_requested.connect(lambda: self.sidebar.select("runs"))
        self.top_bar.command_requested.connect(lambda: self.sidebar.select("home"))
        self.top_bar.refresh_requested.connect(self._refresh_status_from_engine)
        content_layout.addWidget(self.top_bar)
        content_layout.addWidget(self.stack, stretch=1)

        layout.addWidget(self.sidebar)
        layout.addWidget(content, stretch=1)
        self.setCentralWidget(central)

        self._build_status_bar()
        self.sidebar.select("home")
        self._refresh_status_from_engine()

    # -- status bar -----------------------------------------------------

    def _build_status_bar(self) -> None:
        status = QStatusBar()
        self._project_label = make_project_label()
        self._run_label = make_run_label()
        self._llm_label = make_llm_label()

        separator = QLabel("|")
        separator.setObjectName("StatusItem")

        status.addWidget(self._project_label)
        status.addPermanentWidget(self._run_label)
        status.addPermanentWidget(separator)
        status.addPermanentWidget(self._llm_label)
        self.setStatusBar(status)

    def _refresh_status_from_engine(self) -> None:
        info = self.engine.current_project()
        if info is None:
            self._project_label.setText("No project")
        else:
            self._project_label.setText(f"Project: {info.name}")
        latest = self.engine.latest_run_id()
        self._run_label.setText(f"Run: {latest}" if latest else "Run: -")
        self._llm_label.setText(llm_indicator_text())
        self._refresh_top_bar()

    def _update_status_project(self, info) -> None:
        self._project_label.setText(f"Project: {info.name}")
        latest = self.engine.latest_run_id()
        self._run_label.setText(f"Run: {latest}" if latest else "Run: -")
        self._llm_label.setText(llm_indicator_text())
        self._refresh_top_bar()

    def _update_status_run(self, run_id: str) -> None:
        self._run_label.setText(f"Run: {run_id}")
        self._refresh_top_bar()

    def _refresh_top_bar(self) -> None:
        project = self.engine.current_project()
        try:
            gateway = self.engine.gateway_status()
        except Exception:  # noqa: BLE001 - status must not break navigation
            gateway = None
        self.top_bar.set_context(
            page=self.sidebar.current_label(),
            project=project,
            gateway=gateway,
            llm_text=llm_indicator_text(),
        )

    # -- navigation -----------------------------------------------------

    def _on_section_selected(self, key: str) -> None:
        page = self.pages.get(key)
        if page is not None:
            self.stack.setCurrentWidget(page)
            self._refresh_status_from_engine()

    def _open_project_from_home(self) -> None:
        self.sidebar.select("projects")
        projects = self.pages.get("projects")
        open_project = getattr(projects, "open_project_dialog", None)
        if callable(open_project):
            open_project()

    def _init_project_from_home(self) -> None:
        self.sidebar.select("projects")
        projects = self.pages.get("projects")
        init_project = getattr(projects, "init_project_dialog", None)
        if callable(init_project):
            init_project()

    def _start_run_from_home(self, task: str) -> None:
        self.sidebar.select("runs")
        runs = self.pages.get("runs")
        set_task = getattr(runs, "set_task", None)
        if callable(set_task):
            set_task(task, start=True)

    def _jump_to_artifact(self, run_id: str, path) -> None:
        artifacts = self.pages.get("artifacts")
        if artifacts is None:
            return
        self.sidebar.select("artifacts")
        focus = getattr(artifacts, "focus_artifact", None)
        if callable(focus):
            focus(run_id, path)

    # -- shutdown -------------------------------------------------------

    def _running_jobs(self) -> list[QThread]:
        jobs: list[QThread] = []
        for page in self.pages.values():
            for attr in ("_job", "_auth_job"):
                job = getattr(page, attr, None)
                if isinstance(job, QThread) and job.isRunning():
                    jobs.append(job)
        return jobs

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        jobs = self._running_jobs()
        if jobs:
            if not self._headless:
                confirm = QMessageBox.question(
                    self,
                    "Jobs still running",
                    "A step is still running (possibly a GitHub write).\n"
                    "Closing now may leave it half-finished. Close anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if confirm != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
            for job in jobs:
                job.requestInterruption()
            for job in jobs:
                # Give threads a chance to finish; force-stop as a last resort
                # so Qt does not abort with "Destroyed while thread is running".
                if not job.wait(5000):
                    job.terminate()
                    job.wait(2000)
        event.accept()
