from __future__ import annotations

from parallel_agents.desktop._qt import QApplication

QSS = """
* { font-family: "Segoe UI", "Inter", system-ui, sans-serif; font-size: 13px; }

QMainWindow, QWidget { background: #0f1115; color: #e6e8ec; }

#Sidebar {
    background: #0a0c10;
    border-right: 1px solid #1c2030;
    min-width: 220px;
    max-width: 260px;
}
#SidebarHeader {
    color: #7b8294;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.2px;
    padding: 18px 18px 8px 18px;
    text-transform: uppercase;
}
QPushButton#NavButton {
    background: transparent;
    color: #c9cdd6;
    border: none;
    text-align: left;
    padding: 10px 18px;
    border-left: 3px solid transparent;
}
QPushButton#NavButton:hover { background: #141826; color: #ffffff; }
QPushButton#NavButton:checked {
    background: #141826;
    color: #ffffff;
    border-left: 3px solid #5b8def;
}

#PageHeader {
    font-size: 22px;
    font-weight: 600;
    padding: 24px 32px 4px 32px;
}
#PageSubtitle {
    color: #8a90a2;
    padding: 0 32px 18px 32px;
}

QFrame#Card {
    background: #151823;
    border: 1px solid #1f2434;
    border-radius: 10px;
}

QPushButton {
    background: #1b1f2c;
    color: #e6e8ec;
    border: 1px solid #262b3d;
    border-radius: 6px;
    padding: 8px 14px;
}
QPushButton:hover { background: #232940; }
QPushButton#Primary {
    background: #3d6fe0;
    border: 1px solid #3d6fe0;
    color: white;
}
QPushButton#Primary:hover { background: #4a7cf0; }
QPushButton#Danger {
    background: #2a1820;
    color: #ff7a90;
    border: 1px solid #4a2030;
}
QPushButton#Danger:hover { background: #3a1c28; }

QLineEdit, QPlainTextEdit, QTextBrowser, QListWidget, QTreeWidget {
    background: #0c0f17;
    color: #e6e8ec;
    border: 1px solid #1f2434;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #3d6fe0;
}

QStatusBar { background: #0a0c10; color: #7b8294; border-top: 1px solid #1c2030; }

QLabel#WorkerStatusIdle  { color: #6a7185; }
QLabel#WorkerStatusRunning { color: #f0b146; }
QLabel#WorkerStatusDone   { color: #4ad08b; }
QLabel#WorkerStatusError  { color: #ff7a90; }
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
