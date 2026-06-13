from __future__ import annotations

import os

from parallel_agents.desktop._qt import (
    QComboBox,
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
from parallel_agents.desktop.services.settings_store import (
    KNOWN_KEYS,
    MODEL_CHOICES,
    PERMISSION_MODE_CHOICES,
)

# Per-artifact LLM toggles, in workflow order, with display labels.
_LLM_ARTIFACTS: tuple[tuple[str, str], ...] = (
    ("BRIEF", "Brief"),
    ("PRFAQ", "PR/FAQ"),
    ("TECH_STACK", "Tech stack"),
    ("RFC", "Architecture RFC"),
    ("ROADMAP", "Roadmap"),
    ("SPRINT", "Sprint"),
)

# Tri-state: Default = let the policy decide (on when a key is present);
# On = force LLM; Off = force deterministic template.
_TRISTATE = ("Default", "On", "Off")
_TRISTATE_TO_VALUE = {"Default": "", "On": "1", "Off": "0"}


def _make_combo(choices: tuple[str, ...], editable: bool = True) -> QComboBox:
    combo = QComboBox()
    combo.addItems(choices)
    combo.setEditable(editable)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    return combo


def _set_combo_value(combo: QComboBox, value: str) -> None:
    if not value:
        combo.setCurrentIndex(0)
        return
    idx = combo.findText(value)
    if idx >= 0:
        combo.setCurrentIndex(idx)
    else:
        combo.setEditText(value)


def _env_to_tristate(name: str) -> str:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return "Default"
    return "On" if raw.strip().lower() in {"1", "true", "yes", "on"} else "Off"


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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setVerticalSpacing(8)
        self.planner_model = _make_combo(MODEL_CHOICES)
        self.judge_model = _make_combo(MODEL_CHOICES)
        self.permission_mode = _make_combo(PERMISSION_MODE_CHOICES, editable=False)
        self.llm_model = _make_combo(("",) + MODEL_CHOICES)
        self.gateway_key = QLineEdit()
        self.gateway_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.gateway_key.setPlaceholderText("Leave blank to disable auth")

        form.addRow("Planner model", self.planner_model)
        form.addRow("Judge model", self.judge_model)
        form.addRow("Permission mode", self.permission_mode)
        form.addRow("LLM model (all generators)", self.llm_model)
        form.addRow("Gateway API key", self.gateway_key)
        layout.addLayout(form)

        llm_header = QLabel("LLM-backed generation")
        llm_header.setStyleSheet(
            "font-size: 11px; font-weight: 600; letter-spacing: 1.2px;"
            " text-transform: uppercase; color: #8a90a2; padding-top: 8px;"
        )
        layout.addWidget(llm_header)

        flag_hint = QLabel(
            "Default = on when an ANTHROPIC_API_KEY is set, off otherwise. "
            "On forces the LLM; Off forces deterministic templates. Any artifact "
            "falls back to a template if the key is missing or generation fails."
        )
        flag_hint.setStyleSheet("color: #8a90a2; font-size: 12px;")
        flag_hint.setWordWrap(True)
        layout.addWidget(flag_hint)

        llm_form = QFormLayout()
        llm_form.setVerticalSpacing(8)
        self.llm_global = _make_combo(_TRISTATE, editable=False)
        llm_form.addRow("All generators", self.llm_global)
        self.llm_flags: dict[str, QComboBox] = {}
        for key, label in _LLM_ARTIFACTS:
            combo = _make_combo(_TRISTATE, editable=False)
            self.llm_flags[key] = combo
            llm_form.addRow(label, combo)
        layout.addLayout(llm_form)

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
        self.status.setStyleSheet("color: #8a90a2; font-size: 12px;")
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
        _set_combo_value(self.planner_model, os.environ.get("PA_PLANNER_MODEL", "opus"))
        _set_combo_value(self.judge_model, os.environ.get("PA_JUDGE_MODEL", "opus"))
        _set_combo_value(
            self.permission_mode, os.environ.get("PA_PERMISSION_MODE", "default")
        )
        _set_combo_value(self.llm_model, os.environ.get("PA_DESKTOP_LLM_MODEL", ""))
        self.gateway_key.setText(os.environ.get("PA_GATEWAY_API_KEY", ""))
        _set_combo_value(self.llm_global, _env_to_tristate("PA_DESKTOP_LLM"))
        for key, combo in self.llm_flags.items():
            _set_combo_value(combo, _env_to_tristate(f"PA_DESKTOP_LLM_{key}"))

    def _collect(self) -> dict[str, str]:
        values = {
            "PA_PLANNER_MODEL": self.planner_model.currentText().strip(),
            "PA_JUDGE_MODEL": self.judge_model.currentText().strip(),
            "PA_PERMISSION_MODE": self.permission_mode.currentText().strip(),
            "PA_GATEWAY_API_KEY": self.gateway_key.text(),
            "PA_DESKTOP_LLM_MODEL": self.llm_model.currentText().strip(),
            "PA_DESKTOP_LLM": _TRISTATE_TO_VALUE.get(self.llm_global.currentText(), ""),
        }
        for key, combo in self.llm_flags.items():
            values[f"PA_DESKTOP_LLM_{key}"] = _TRISTATE_TO_VALUE.get(
                combo.currentText(), ""
            )
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
