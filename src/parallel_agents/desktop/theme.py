from __future__ import annotations

from parallel_agents.desktop._qt import QApplication

# Palette
BG          = "#0f1115"
BG_PANEL    = "#0a0c10"
BG_CARD     = "#151823"
BG_CARD_HI  = "#1a1e2d"
BG_INPUT    = "#0c0f17"
BORDER      = "#1f2434"
BORDER_HI   = "#2a3149"
TEXT        = "#e6e8ec"
TEXT_DIM    = "#8a90a2"
TEXT_FAINT  = "#6a7185"
ACCENT      = "#5b8def"
ACCENT_HI   = "#7aa3ff"
SUCCESS     = "#4ad08b"
WARNING     = "#f0b146"
DANGER      = "#ff7a90"

QSS = f"""
* {{ font-family: "Segoe UI", "Inter", system-ui, sans-serif; font-size: 13px; }}

QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; }}

#Sidebar {{
    background: {BG_PANEL};
    border-right: 1px solid {BORDER};
    min-width: 220px;
    max-width: 260px;
}}
#SidebarHeader {{
    color: {TEXT_FAINT};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.2px;
    padding: 18px 18px 8px 18px;
    text-transform: uppercase;
}}
QPushButton#NavButton {{
    background: transparent;
    color: #c9cdd6;
    border: none;
    text-align: left;
    padding: 10px 18px;
    border-left: 3px solid transparent;
}}
QPushButton#NavButton:hover {{ background: #141826; color: #ffffff; }}
QPushButton#NavButton:checked {{
    background: #141826;
    color: #ffffff;
    border-left: 3px solid {ACCENT};
}}

#PageHeader {{
    font-size: 22px;
    font-weight: 600;
    padding: 24px 32px 4px 32px;
}}
#PageSubtitle {{
    color: {TEXT_DIM};
    padding: 0 32px 18px 32px;
}}

QFrame#Card {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QFrame#Card:hover {{
    background: {BG_CARD_HI};
    border: 1px solid {BORDER_HI};
}}

QPushButton {{
    background: #1b1f2c;
    color: {TEXT};
    border: 1px solid #262b3d;
    border-radius: 6px;
    padding: 8px 14px;
}}
QPushButton:hover {{ background: #232940; border-color: {BORDER_HI}; }}
QPushButton:disabled {{ color: {TEXT_FAINT}; background: #15192a; border-color: {BORDER}; }}
QPushButton#Primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: white;
}}
QPushButton#Primary:hover {{ background: {ACCENT_HI}; border-color: {ACCENT_HI}; }}
QPushButton#Primary:disabled {{ background: #2a3760; border-color: #2a3760; color: #93a3c9; }}
QPushButton#Danger {{
    background: #2a1820;
    color: {DANGER};
    border: 1px solid #4a2030;
}}
QPushButton#Danger:hover {{ background: #3a1c28; }}

QLineEdit, QPlainTextEdit, QTextBrowser, QListWidget, QTreeWidget {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus,
QListWidget:focus, QTreeWidget:focus {{
    border: 1px solid {ACCENT};
}}

QCheckBox {{ spacing: 8px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 1px solid {BORDER_HI};
    border-radius: 3px;
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    image: none;
}}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 4px 2px 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #2a3149; border-radius: 4px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: #3a4366; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QStatusBar {{
    background: {BG_PANEL};
    color: {TEXT_FAINT};
    border-top: 1px solid {BORDER};
}}
QLabel#StatusItem {{
    color: {TEXT_DIM};
    padding: 0 10px;
    border-left: 1px solid {BORDER};
}}

/* status pills used by WorkerTile and step cards */
QLabel#WorkerStatusIdle {{
    color: {TEXT_FAINT};
    background: #1a1f2e;
    padding: 2px 8px;
    border-radius: 9px;
    font-size: 11px;
}}
QLabel#WorkerStatusRunning {{
    color: {WARNING};
    background: #2a2316;
    padding: 2px 8px;
    border-radius: 9px;
    font-size: 11px;
}}
QLabel#WorkerStatusDone {{
    color: {SUCCESS};
    background: #14291f;
    padding: 2px 8px;
    border-radius: 9px;
    font-size: 11px;
}}
QLabel#WorkerStatusError {{
    color: {DANGER};
    background: #2a1820;
    padding: 2px 8px;
    border-radius: 9px;
    font-size: 11px;
}}

/* empty state */
#EmptyStateCard {{
    background: {BG_CARD};
    border: 1px dashed {BORDER_HI};
    border-radius: 12px;
    min-width: 360px;
    max-width: 480px;
}}
QLabel#EmptyStateGlyph {{ color: {TEXT_FAINT}; font-size: 36px; }}
QLabel#EmptyStateTitle {{ color: {TEXT}; font-size: 16px; font-weight: 600; }}
QLabel#EmptyStateHint  {{ color: {TEXT_DIM}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
