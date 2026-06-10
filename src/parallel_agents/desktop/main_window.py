from __future__ import annotations

from parallel_agents.desktop._qt import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QThread,
    QWidget,
)
from parallel_agents.desktop.pages.approvals_page import ApprovalsPage
from parallel_agents.desktop.pages.artifacts_page import ArtifactsPage
from parallel_agents.desktop.pages.company_page import CompanyPage
from parallel_agents.desktop.pages.projects_page import ProjectsPage
from parallel_agents.desktop.pages.runs_page import RunsPage
from parallel_agents.desktop.pages.settings_page import SettingsPage
from parallel_agents.desktop.services.engine import EngineService
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

        self.engine = EngineService()
        # Apply persisted user-level settings on launch (project ones load on open).
        self.engine.settings_store().load()

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(
            sections=[
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

        self.pages: dict[str, QWidget] = {
            "projects": projects_page,
            "company": company_page,
            "runs": runs_page,
            "approvals": ApprovalsPage(self.engine),
            "artifacts": artifacts_page,
            "settings": SettingsPage(self.engine),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, stretch=1)
        self.setCentralWidget(central)

        self._build_status_bar()
        self.sidebar.select("projects")
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

    def _update_status_project(self, info) -> None:
        self._project_label.setText(f"Project: {info.name}")
        latest = self.engine.latest_run_id()
        self._run_label.setText(f"Run: {latest}" if latest else "Run: -")
        self._llm_label.setText(llm_indicator_text())

    def _update_status_run(self, run_id: str) -> None:
        self._run_label.setText(f"Run: {run_id}")

    # -- navigation -----------------------------------------------------

    def _on_section_selected(self, key: str) -> None:
        page = self.pages.get(key)
        if page is not None:
            self.stack.setCurrentWidget(page)
            self._refresh_status_from_engine()

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
