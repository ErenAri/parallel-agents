"""Single source of truth for which desktop artifact generators use the LLM.

Default-on policy: when an ANTHROPIC_API_KEY is present, LLM generation is the
default for every artifact. A per-artifact flag (``PA_DESKTOP_LLM_<KEY>``) or a
global flag (``PA_DESKTOP_LLM``) overrides that default in either direction, so
users can force-enable without a key (it will fall back) or force-disable with
one. No Qt imports — safe for the status bar and the engine alike.
"""

from __future__ import annotations

import os

# Artifact key (env-flag suffix) -> short human label for the status bar.
ARTIFACTS: dict[str, str] = {
    "BRIEF": "brief",
    "PRFAQ": "prfaq",
    "TECH_STACK": "stack",
    "RFC": "rfc",
    "ROADMAP": "roadmap",
    "SPRINT": "sprint",
}


def _truthy(value: str | None) -> bool:
    return bool(value) and value.strip().lower() in {"1", "true", "yes", "on"}


def _explicit(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None:
        return None
    return _truthy(raw)


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def llm_enabled(artifact_key: str) -> bool:
    """Whether the LLM generator should run for one artifact.

    Precedence: per-artifact flag > global flag > (key present?).
    """
    per = _explicit(f"PA_DESKTOP_LLM_{artifact_key}")
    if per is not None:
        return per
    glob = _explicit("PA_DESKTOP_LLM")
    if glob is not None:
        return glob
    return llm_available()


def active_generators() -> list[str]:
    return [label for key, label in ARTIFACTS.items() if llm_enabled(key)]
