from __future__ import annotations

from parallel_agents.desktop._qt import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Parallel Agents Office")

        self.engine = EngineService()

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
        company_page.artifact_created.connect(
            lambda run_id, path: self._jump_to_artifact(run_id, path)
        )
        self.pages: dict[str, QWidget] = {
            "projects": ProjectsPage(self.engine),
            "company": company_page,
            "runs": RunsPage(self.engine),
            "approvals": ApprovalsPage(self.engine),
            "artifacts": artifacts_page,
            "settings": SettingsPage(self.engine),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, stretch=1)
        self.setCentralWidget(central)

        status = QStatusBar()
        status.showMessage("Ready")
        self.setStatusBar(status)

        self.sidebar.select("projects")

    def _on_section_selected(self, key: str) -> None:
        page = self.pages.get(key)
        if page is not None:
            self.stack.setCurrentWidget(page)
            self.statusBar().showMessage(f"Viewing: {key}")

    def _jump_to_artifact(self, run_id: str, path) -> None:
        artifacts = self.pages.get("artifacts")
        if artifacts is None:
            return
        self.sidebar.select("artifacts")
        focus = getattr(artifacts, "focus_artifact", None)
        if callable(focus):
            focus(run_id, path)
