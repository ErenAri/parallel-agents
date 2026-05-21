from __future__ import annotations

import sys

from parallel_agents.desktop._qt import QApplication
from parallel_agents.desktop.main_window import MainWindow
from parallel_agents.desktop.theme import apply_theme


def run(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Parallel Agents Office")
    app.setOrganizationName("Parallel Agents")
    apply_theme(app)

    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    return app.exec()
