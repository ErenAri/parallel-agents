"""Construction smoke: instantiates the full desktop window (and thus every page)
under a stubbed PySide6, so signature/wiring bugs in __init__ are caught without a
real Qt runtime. The import smoke only imports modules; this one constructs them.

Run from repo root:

    python scripts/smoke_desktop_construct.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Reuse the exact PySide6 stub the import smoke installs.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke_desktop_imports import _install_pyside6_stub  # noqa: E402


def main() -> int:
    repo_src = Path(__file__).resolve().parent.parent / "src"
    sys.path.insert(0, str(repo_src))
    _install_pyside6_stub()

    from parallel_agents.desktop.main_window import MainWindow

    # MainWindow.__init__ constructs every page (Projects, Company, Runs,
    # Approvals, Artifacts, Settings) with a real EngineService that has no
    # project open, so __init__ wiring runs end-to-end under the stub.
    try:
        MainWindow()
    except Exception as exc:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print(f"\nFAIL: MainWindow construction raised {type(exc).__name__}: {exc}")
        return 1

    print("OK: MainWindow and all pages construct cleanly under the PySide6 stub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
