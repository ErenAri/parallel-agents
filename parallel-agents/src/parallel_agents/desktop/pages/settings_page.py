from __future__ import annotations

import os

from parallel_agents.desktop._qt import (
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService


class SettingsPage(Page):
    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Settings",
            subtitle="Configure engine and gateway options. Values map to PA_* environment variables.",
        )
        self.engine = engine

        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)

        form = QFormLayout()
        self.planner_model = QLineEdit(os.environ.get("PA_PLANNER_MODEL", "opus"))
        self.judge_model = QLineEdit(os.environ.get("PA_JUDGE_MODEL", "opus"))
        self.permission_mode = QLineEdit(os.environ.get("PA_PERMISSION_MODE", "default"))
        self.gateway_key = QLineEdit(os.environ.get("PA_GATEWAY_API_KEY", ""))
        self.gateway_key.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Planner model", self.planner_model)
        form.addRow("Judge model", self.judge_model)
        form.addRow("Permission mode", self.permission_mode)
        form.addRow("Gateway API key", self.gateway_key)
        layout.addLayout(form)

        save = QPushButton("Apply for this session")
        save.setObjectName("Primary")
        save.clicked.connect(self._apply)
        layout.addWidget(save)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #8a90a2; padding-top: 4px;")
        layout.addWidget(self.status)

        self.body_layout.addWidget(card)
        self.body_layout.addStretch(1)

    def _apply(self) -> None:
        os.environ["PA_PLANNER_MODEL"] = self.planner_model.text()
        os.environ["PA_JUDGE_MODEL"] = self.judge_model.text()
        os.environ["PA_PERMISSION_MODE"] = self.permission_mode.text()
        if self.gateway_key.text():
            os.environ["PA_GATEWAY_API_KEY"] = self.gateway_key.text()
        self.status.setText("Applied to this process. Persisted config: TODO.")
