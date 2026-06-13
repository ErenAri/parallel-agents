from __future__ import annotations

import os
import sys
import traceback

from parallel_agents.desktop._qt import QApplication, QMessageBox, QTimer
from parallel_agents.desktop.main_window import MainWindow
from parallel_agents.desktop.theme import apply_theme


def _install_excepthook() -> None:
    """Surface unhandled exceptions in windowed builds instead of dying silently."""

    def _hook(exc_type, exc, tb) -> None:
        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        sys.stderr.write(detail)
        try:
            QMessageBox.critical(
                None,
                "Unexpected error",
                f"{exc_type.__name__}: {exc}\n\n{detail[-3000:]}",
            )
        except Exception:  # noqa: BLE001 - never raise from the hook itself
            pass

    sys.excepthook = _hook


def run(argv: list[str] | None = None) -> int:
    raw = list(sys.argv if argv is None else argv)
    # --smoke (or PA_DESKTOP_SMOKE=1) builds the full window and exits 0 without
    # entering the event loop. Used by CI to verify a packaged binary actually
    # launches and constructs under an offscreen Qt platform.
    smoke = "--smoke" in raw or os.environ.get("PA_DESKTOP_SMOKE") == "1"
    qt_argv = [arg for arg in raw if arg != "--smoke"]

    app = QApplication(qt_argv)
    app.setApplicationName("Parallel Agents Office")
    app.setOrganizationName("Parallel Agents")
    apply_theme(app)
    _install_excepthook()

    window = MainWindow()
    window.resize(1280, 800)
    if smoke:
        # Build the window, let Qt initialize, then close cleanly without the
        # interactive "jobs still running" prompt (which would block offscreen).
        window._headless = True
        window.show()
        QTimer.singleShot(0, window.close)
        QTimer.singleShot(0, app.quit)
        return app.exec()
    window.show()
    return app.exec()
