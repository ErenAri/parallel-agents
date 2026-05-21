"""Parallel Agents Office desktop application (PySide6).

Install with: pip install parallel-agents[desktop]
Launch with:  parallel-agents-desktop  (or  python -m parallel_agents.desktop)

`run` is imported lazily so that other desktop modules (e.g. services.engine)
can be used in headless contexts without requiring PySide6.
"""

from __future__ import annotations

from typing import Any

__all__ = ["run"]


def __getattr__(name: str) -> Any:
    if name == "run":
        from parallel_agents.desktop.app import run as _run

        return _run
    raise AttributeError(name)
