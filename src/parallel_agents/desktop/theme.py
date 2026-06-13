"""Design tokens + QSS for the Parallel Agents Office desktop app.

Token philosophy (Linear / Vercel / Sentry-class dark UI):
  - Restricted palette: monochrome greys + one accent. Status uses dots,
    not full chip backgrounds.
  - 4px spacing scale, no ad-hoc values.
  - Type scale: 11 caps / 12 meta / 13 body / 15 title / 18 section / 24 page.
  - Four elevation tiers from sidebar (0) up to modal (4).
"""

from __future__ import annotations

from parallel_agents.desktop._qt import QApplication

# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

# Spacing scale (multiples of 4)
S1, S2, S3, S4, S5, S6, S7 = 4, 8, 12, 16, 20, 24, 32

# Type scale
FS_CAPS    = 11   # uppercase tracked labels
FS_META    = 12   # dim secondary text
FS_BODY    = 13   # body
FS_TITLE   = 15   # card/section titles
FS_SECTION = 18   # subsection headers
FS_PAGE    = 24   # page header

# Elevation surfaces — order: deepest to highest
ELEV_0     = "#0a0c10"  # sidebar / status bar (sunk)
ELEV_1     = "#0f1115"  # base canvas
ELEV_2     = "#151823"  # cards
ELEV_3     = "#1a1e2d"  # hovered card / nav active
ELEV_4     = "#1f2434"  # input / modal surface

# Borders — desaturated, near-neutral
BORDER     = "#1f2434"
BORDER_HI  = "#2a3149"

# Text
TEXT_HI    = "#f0f2f7"  # headings, key data
TEXT       = "#c9cdd6"  # body
TEXT_DIM   = "#8a90a2"  # secondary
TEXT_FAINT = "#5d6478"  # tertiary / placeholder

# Accent — exactly one
ACCENT     = "#5b8def"
ACCENT_HI  = "#7aa3ff"
ACCENT_LO  = "#22315c"  # subdued tint for hover/selected backgrounds

# Status dots only (text and pill backgrounds stay neutral; dot carries meaning)
DOT_IDLE    = "#5d6478"
DOT_RUNNING = "#d4a83a"
DOT_DONE    = "#3aa873"
DOT_ERROR   = "#d76377"


# ---------------------------------------------------------------------------
# QSS
# ---------------------------------------------------------------------------

QSS = f"""
* {{
    font-family: "Inter", "Segoe UI Variable", "Segoe UI", system-ui, sans-serif;
    font-size: {FS_BODY}px;
    color: {TEXT};
}}

QMainWindow, QWidget {{ background: {ELEV_1}; }}

/* ---------------- Sidebar ---------------- */
#Sidebar {{
    background: {ELEV_0};
    border-right: 1px solid {BORDER};
    min-width: 220px;
    max-width: 240px;
}}
#SidebarHeader {{
    color: {TEXT_FAINT};
    font-size: {FS_CAPS}px;
    font-weight: 600;
    letter-spacing: 1.4px;
    padding: {S5}px {S4}px {S2}px {S4}px;
    text-transform: uppercase;
}}
QPushButton#NavButton {{
    background: transparent;
    color: {TEXT};
    border: none;
    text-align: left;
    padding: {S2}px {S4}px;
    border-left: 2px solid transparent;
    font-size: {FS_BODY}px;
}}
QPushButton#NavButton:hover {{ background: {ELEV_2}; color: {TEXT_HI}; }}
QPushButton#NavButton:checked {{
    background: {ELEV_3};
    color: {TEXT_HI};
    border-left: 2px solid {ACCENT};
}}

/* ---------------- Page chrome ---------------- */
#PageHeader {{
    color: {TEXT_HI};
    font-size: {FS_PAGE}px;
    font-weight: 600;
    letter-spacing: -0.3px;
    padding: {S6}px {S7}px {S1}px {S7}px;
}}
#PageSubtitle {{
    color: {TEXT_DIM};
    font-size: {FS_BODY}px;
    padding: 0 {S7}px {S4}px {S7}px;
}}

/* ---------------- Cards ---------------- */
QFrame#Card {{
    background: {ELEV_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#Card:hover {{
    background: {ELEV_3};
    border: 1px solid {BORDER_HI};
}}

/* ---------------- Buttons ---------------- */
QPushButton {{
    background: {ELEV_2};
    color: {TEXT};
    border: 1px solid {BORDER_HI};
    border-radius: 6px;
    padding: {S2}px {S4}px;
    font-size: {FS_BODY}px;
}}
QPushButton:hover {{ background: {ELEV_3}; border-color: {ACCENT_LO}; }}
QPushButton:pressed {{ background: {ELEV_4}; }}
QPushButton:disabled {{
    color: {TEXT_FAINT};
    background: {ELEV_2};
    border-color: {BORDER};
}}
QPushButton#Primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: white;
    font-weight: 500;
}}
QPushButton#Primary:hover {{ background: {ACCENT_HI}; border-color: {ACCENT_HI}; }}
QPushButton#Primary:pressed {{ background: {ACCENT}; }}
QPushButton#Primary:disabled {{
    background: {ACCENT_LO};
    border-color: {ACCENT_LO};
    color: {TEXT_DIM};
}}
QPushButton#Danger {{
    background: transparent;
    color: {DOT_ERROR};
    border: 1px solid {BORDER_HI};
}}
QPushButton#Danger:hover {{ background: {ELEV_3}; border-color: {DOT_ERROR}; }}

/* ---------------- Inputs ---------------- */
QLineEdit, QPlainTextEdit, QTextBrowser, QListWidget, QTreeWidget {{
    background: {ELEV_4};
    color: {TEXT_HI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: {S2}px {S3}px;
    selection-background-color: {ACCENT};
    selection-color: white;
    font-size: {FS_BODY}px;
}}
QLineEdit::placeholder, QPlainTextEdit::placeholder {{ color: {TEXT_FAINT}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus,
QListWidget:focus, QTreeWidget:focus {{
    border: 1px solid {ACCENT};
    background: {ELEV_4};
}}

/* ---------------- ComboBox ---------------- */
QComboBox {{
    background: {ELEV_4};
    color: {TEXT_HI};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: {S2}px {S3}px;
    font-size: {FS_BODY}px;
    min-height: 20px;
}}
QComboBox:hover {{ border-color: {BORDER_HI}; }}
QComboBox:focus, QComboBox:on {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 22px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_DIM};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {ELEV_4};
    color: {TEXT_HI};
    border: 1px solid {BORDER_HI};
    border-radius: 6px;
    padding: {S1}px;
    selection-background-color: {ACCENT_LO};
    selection-color: {TEXT_HI};
    outline: 0;
}}

/* ---------------- Checkboxes ---------------- */
QCheckBox {{ spacing: {S2}px; color: {TEXT}; font-size: {FS_BODY}px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {BORDER_HI};
    border-radius: 3px;
    background: {ELEV_4};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
}}

/* ---------------- Scrollbar ---------------- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: {S1}px {S1}px {S1}px {S1}px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_HI};
    border-radius: 3px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_FAINT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ---------------- Status bar ---------------- */
QStatusBar {{
    background: {ELEV_0};
    color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
}}
QStatusBar::item {{ border: none; }}
QLabel#StatusItem {{
    color: {TEXT_DIM};
    font-size: {FS_META}px;
    padding: 0 {S3}px;
    border-left: 1px solid {BORDER};
}}

/* ---------------- App shell ---------------- */
QFrame#TopBar {{
    background: {ELEV_1};
    border-bottom: 1px solid {BORDER};
}}
QLabel#TopBarTitle {{
    color: {TEXT_HI};
    font-size: {FS_TITLE}px;
    font-weight: 600;
}}
QLabel#TopBarMeta {{
    color: {TEXT_DIM};
    font-size: {FS_META}px;
}}
QLabel#TopBarPill {{
    color: {TEXT};
    background: {ELEV_2};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: {S1}px {S3}px;
    font-size: {FS_META}px;
}}

/* ---------------- Design system widgets ---------------- */
QLabel#SectionHeader {{
    color: {TEXT_HI};
    font-size: {FS_SECTION}px;
    font-weight: 600;
    letter-spacing: -0.2px;
}}
QLabel#SectionHint {{
    color: {TEXT_DIM};
    font-size: {FS_BODY}px;
}}
QLabel#CardTitle {{
    color: {TEXT_HI};
    font-size: {FS_TITLE}px;
    font-weight: 600;
}}
QLabel#CardMeta {{
    color: {TEXT_DIM};
    font-size: {FS_META}px;
}}
QLabel#StatValue {{
    color: {TEXT_HI};
    font-size: 22px;
    font-weight: 650;
    letter-spacing: -0.4px;
}}
QLabel#StatLabel {{
    color: {TEXT_DIM};
    font-size: {FS_CAPS}px;
    font-weight: 650;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
QLabel#StatusDotIdle,
QLabel#StatusDotRunning,
QLabel#StatusDotDone,
QLabel#StatusDotError {{
    font-size: {FS_META}px;
    font-weight: 700;
}}
QLabel#StatusDotIdle {{ color: {DOT_IDLE}; }}
QLabel#StatusDotRunning {{ color: {DOT_RUNNING}; }}
QLabel#StatusDotDone {{ color: {DOT_DONE}; }}
QLabel#StatusDotError {{ color: {DOT_ERROR}; }}
QLineEdit#CommandInput {{
    min-height: 42px;
    border-radius: 8px;
    padding: {S2}px {S4}px;
    font-size: {FS_TITLE}px;
}}
QFrame#HeroCard {{
    background: {ELEV_2};
    border: 1px solid {BORDER_HI};
    border-radius: 12px;
}}

/* ---------------- Status pills (dot + text, no chip) ---------------- */
QLabel#WorkerStatusIdle,
QLabel#WorkerStatusRunning,
QLabel#WorkerStatusDone,
QLabel#WorkerStatusError {{
    font-size: {FS_CAPS}px;
    font-weight: 600;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    padding: 0;
    background: transparent;
    border: none;
}}
QLabel#WorkerStatusIdle    {{ color: {DOT_IDLE}; }}
QLabel#WorkerStatusRunning {{ color: {DOT_RUNNING}; }}
QLabel#WorkerStatusDone    {{ color: {DOT_DONE}; }}
QLabel#WorkerStatusError   {{ color: {DOT_ERROR}; }}

/* ---------------- Empty state ---------------- */
#EmptyStateCard {{
    background: {ELEV_2};
    border: 1px dashed {BORDER_HI};
    border-radius: 10px;
    min-width: 360px;
    max-width: 480px;
}}
QLabel#EmptyStateGlyph {{ color: {TEXT_FAINT}; font-size: 36px; }}
QLabel#EmptyStateTitle {{
    color: {TEXT_HI};
    font-size: {FS_TITLE}px;
    font-weight: 600;
}}
QLabel#EmptyStateHint {{ color: {TEXT_DIM}; font-size: {FS_BODY}px; }}

/* ---------------- Tooltip ---------------- */
QToolTip {{
    background: {ELEV_4};
    color: {TEXT_HI};
    border: 1px solid {BORDER_HI};
    border-radius: 4px;
    padding: {S1}px {S2}px;
    font-size: {FS_META}px;
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
