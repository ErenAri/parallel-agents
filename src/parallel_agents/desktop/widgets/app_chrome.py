from __future__ import annotations

from parallel_agents.desktop._qt import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    Signal,
)
from parallel_agents.desktop.services.engine import GatewayLifecycleStatus, ProjectInfo


class TopBar(QFrame):
    command_requested = Signal()
    run_requested = Signal()
    refresh_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("TopBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        title_block = QFrame()
        title_layout = QHBoxLayout(title_block)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)

        self.page_label = QLabel("Command Center")
        self.page_label.setObjectName("TopBarTitle")
        self.project_label = QLabel("No project")
        self.project_label.setObjectName("TopBarMeta")
        title_layout.addWidget(self.page_label)
        title_layout.addWidget(self.project_label)

        layout.addWidget(title_block, stretch=1)

        self.gateway_label = QLabel("Gateway: —")
        self.gateway_label.setObjectName("TopBarPill")
        self.llm_label = QLabel("LLM: —")
        self.llm_label.setObjectName("TopBarPill")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self.command_btn = QPushButton("Ctrl+K")
        self.command_btn.setToolTip("Command palette placeholder")
        self.command_btn.clicked.connect(self.command_requested.emit)
        self.run_btn = QPushButton("New Run")
        self.run_btn.setObjectName("Primary")
        self.run_btn.clicked.connect(self.run_requested.emit)

        layout.addWidget(self.gateway_label)
        layout.addWidget(self.llm_label)
        layout.addWidget(self.refresh_btn)
        layout.addWidget(self.command_btn)
        layout.addWidget(self.run_btn)

    def set_context(
        self,
        *,
        page: str,
        project: ProjectInfo | None,
        gateway: GatewayLifecycleStatus | None,
        llm_text: str,
    ) -> None:
        self.page_label.setText(page)
        self.project_label.setText(project.name if project else "No project")
        self.llm_label.setText(llm_text)
        if gateway is None:
            self.gateway_label.setText("Gateway: —")
        elif gateway.running:
            owner = "desktop" if gateway.owned else gateway.source
            self.gateway_label.setText(f"Gateway: live · {owner}")
        else:
            self.gateway_label.setText("Gateway: stopped")
