from __future__ import annotations

import os

from parallel_agents.desktop._qt import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)
from parallel_agents.desktop.pages._base import Page
from parallel_agents.desktop.services.engine import EngineService
from parallel_agents.desktop.services.settings_store import KNOWN_KEYS


class SettingsPage(Page):
    def __init__(self, engine: EngineService) -> None:
        super().__init__(
            title="Settings",
            subtitle="Persisted to ~/.parallel-agents-desktop.json (user) or .parallel-agents/desktop.json (project). Project values win.",
        )
        self.engine = engine

        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setVerticalSpacing(8)
        self.planner_model = QLineEdit()
        self.judge_model = QLineEdit()
        self.permission_mode = QLineEdit()
        self.gateway_key = QLineEdit()
        self.gateway_key.setEchoMode(QLineEdit.EchoMode.Password)

        self.llm_brief = QCheckBox("Brief (PA_DESKTOP_LLM_BRIEF)")
        self.llm_prfaq = QCheckBox("PR/FAQ (PA_DESKTOP_LLM_PRFAQ)")
        self.llm_rfc = QCheckBox("RFC (PA_DESKTOP_LLM_RFC)")
        self.llm_model = QLineEdit()
        self.llm_model.setPlaceholderText("claude-sonnet-4-6")

        form.addRow("Planner model", self.planner_model)
        form.addRow("Judge model", self.judge_model)
        form.addRow("Permission mode", self.permission_mode)
        form.addRow("Gateway API key", self.gateway_key)
        form.addRow("LLM model", self.llm_model)
        layout.addLayout(form)

        llm_row = QLabel("LLM-backed generation")
        llm_row.setStyleSheet("font-weight: 600; padding-top: 4px;")
        layout.addWidget(llm_row)
        for cb in (self.llm_brief, self.llm_prfaq, self.llm_rfc):
            layout.addWidget(cb)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.save_user_btn = QPushButton("Save to User")
        self.save_user_btn.clicked.connect(self._save_user)
        button_row.addWidget(self.save_user_btn)
        self.save_project_btn = QPushButton("Save to Project")
        self.save_project_btn.setObjectName("Primary")
        self.save_project_btn.clicked.connect(self._save_project)
        button_row.addWidget(self.save_project_btn)
        layout.addLayout(button_row)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #8a90a2;")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.body_layout.addWidget(card)
        self.body_layout.addStretch(1)

        self._populate_from_env()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._populate_from_env()
        self.save_project_btn.setEnabled(self.engine.current_project() is not None)

    # -- helpers --------------------------------------------------------

    def _populate_from_env(self) -> None:
        self.planner_model.setText(os.environ.get("PA_PLANNER_MODEL", "opus"))
        self.judge_model.setText(os.environ.get("PA_JUDGE_MODEL", "opus"))
        self.permission_mode.setText(os.environ.get("PA_PERMISSION_MODE", "default"))
        self.gateway_key.setText(os.environ.get("PA_GATEWAY_API_KEY", ""))
        self.llm_model.setText(os.environ.get("PA_DESKTOP_LLM_MODEL", ""))
        self.llm_brief.setChecked(_truthy_env("PA_DESKTOP_LLM_BRIEF"))
        self.llm_prfaq.setChecked(_truthy_env("PA_DESKTOP_LLM_PRFAQ"))
        self.llm_rfc.setChecked(_truthy_env("PA_DESKTOP_LLM_RFC"))

    def _collect(self) -> dict[str, str]:
        values = {
            "PA_PLANNER_MODEL": self.planner_model.text().strip(),
            "PA_JUDGE_MODEL": self.judge_model.text().strip(),
            "PA_PERMISSION_MODE": self.permission_mode.text().strip(),
            "PA_GATEWAY_API_KEY": self.gateway_key.text(),
            "PA_DESKTOP_LLM_MODEL": self.llm_model.text().strip(),
            "PA_DESKTOP_LLM_BRIEF": "1" if self.llm_brief.isChecked() else "",
            "PA_DESKTOP_LLM_PRFAQ": "1" if self.llm_prfaq.isChecked() else "",
            "PA_DESKTOP_LLM_RFC": "1" if self.llm_rfc.isChecked() else "",
        }
        return {k: v for k, v in values.items() if k in KNOWN_KEYS}

    def _save_user(self) -> None:
        values = self._collect()
        path = self.engine.settings_store().save_user(values)
        self._apply_env(values)
        self.status.setText(f"Saved to {path}")

    def _save_project(self) -> None:
        if self.engine.current_project() is None:
            self.status.setText("Open a project first to save project-scoped settings.")
            return
        values = self._collect()
        path = self.engine.settings_store().save_project(values)
        self._apply_env(values)
        self.status.setText(f"Saved to {path}")

    @staticmethod
    def _apply_env(values: dict[str, str]) -> None:
        for key, value in values.items():
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)


def _truthy_env(name: str) -> bool:
    value = os.environ.get(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}
