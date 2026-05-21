"""Single import point for PySide6.

Raises a helpful error if the optional `desktop` extra is not installed.
"""

from __future__ import annotations

try:
    from PySide6.QtCore import (  # noqa: F401
        QObject,
        QSize,
        Qt,
        QThread,
        QTimer,
        Signal,
        Slot,
    )
    from PySide6.QtGui import (  # noqa: F401
        QAction,
        QColor,
        QFont,
        QIcon,
        QPalette,
        QTextCharFormat,
        QTextCursor,
    )
    from PySide6.QtWidgets import (  # noqa: F401
        QApplication,
        QCheckBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpacerItem,
        QSplitter,
        QStackedWidget,
        QStatusBar,
        QStyle,
        QTabWidget,
        QTextBrowser,
        QToolBar,
        QTreeWidget,
        QTreeWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - guidance for missing extra
    raise SystemExit(
        "PySide6 is not installed. Install the desktop extra:\n"
        "    pip install parallel-agents[desktop]\n"
    ) from exc
