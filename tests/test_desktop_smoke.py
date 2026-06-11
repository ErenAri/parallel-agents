"""Bring the desktop smoke scripts into the pytest gate.

Each script manipulates sys.modules (installs a PySide6 stub) or constructs the
full Qt window, so they are run as subprocesses in a clean interpreter to avoid
polluting the rest of the suite. This makes `pytest` alone a complete gate for
the desktop surface, instead of relying on the scripts being run by hand.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPTS = [
    "smoke_desktop_imports.py",
    "smoke_desktop_construct.py",
    "smoke_desktop_engine.py",
    "smoke_desktop_polish.py",
]


def _has_pyside6() -> bool:
    import importlib.util

    return importlib.util.find_spec("PySide6") is not None


@pytest.mark.parametrize("script", SMOKE_SCRIPTS)
def test_smoke_script_passes(script):
    path = REPO_ROOT / "scripts" / script
    assert path.exists(), f"missing smoke script: {path}"
    proc = subprocess.run(
        [sys.executable, str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"{script} failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


@pytest.mark.skipif(not _has_pyside6(), reason="PySide6 not installed")
def test_desktop_launches_headless_with_real_qt():
    """The packaged entry point builds the full window under offscreen Qt.

    This is the same path CI uses to smoke-execute the built binary: it exercises
    the real PySide6 stack (not the stub), catching wiring bugs the stub can hide.
    """
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PA_DESKTOP_LLM": "0"}
    env.pop("ANTHROPIC_API_KEY", None)
    proc = subprocess.run(
        [sys.executable, "-m", "parallel_agents.desktop", "--smoke"],
        cwd=REPO_ROOT / "src",
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    assert proc.returncode == 0, (
        f"headless desktop launch failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
