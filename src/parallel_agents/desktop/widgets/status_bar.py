"""Persistent status bar widgets: project | run id | LLM mode."""

from __future__ import annotations

from parallel_agents.desktop._qt import QLabel
from parallel_agents.desktop.services.status import llm_indicator_text

__all__ = [
    "make_project_label",
    "make_run_label",
    "make_llm_label",
    "llm_indicator_text",
]


def make_project_label() -> QLabel:
    label = QLabel("No project")
    label.setObjectName("StatusItem")
    return label


def make_run_label() -> QLabel:
    label = QLabel("·")
    label.setObjectName("StatusItem")
    return label


def make_llm_label() -> QLabel:
    label = QLabel(llm_indicator_text())
    label.setObjectName("StatusItem")
    return label
