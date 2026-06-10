from __future__ import annotations

import sys
import traceback

from parallel_agents.desktop._qt import QApplication, QMessageBox
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
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Parallel Agents Office")
    app.setOrganizationName("Parallel Agents")
    apply_theme(app)
    _install_excepthook()

    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    return app.exec()
