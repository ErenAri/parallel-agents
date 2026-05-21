"""Reusable error dialog with collapsible details and a Copy button."""

from __future__ import annotations

from parallel_agents.desktop._qt import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    Qt,
    QVBoxLayout,
)


class ErrorDialog(QDialog):
    def __init__(
        self,
        parent,
        title: str,
        message: str,
        details: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self._details = details or ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(msg_label)

        self._details_view = QPlainTextEdit()
        self._details_view.setPlainText(self._details)
        self._details_view.setReadOnly(True)
        self._details_view.setVisible(False)
        self._details_view.setMinimumHeight(160)
        layout.addWidget(self._details_view)

        toggle_row = QHBoxLayout()
        self._toggle = QPushButton("Show details")
        self._toggle.clicked.connect(self._toggle_details)
        toggle_row.addWidget(self._toggle)

        self._copy = QPushButton("Copy")
        self._copy.clicked.connect(self._copy_to_clipboard)
        toggle_row.addWidget(self._copy)
        toggle_row.addStretch(1)
        layout.addLayout(toggle_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        if not self._details:
            self._toggle.setVisible(False)
            self._copy.setVisible(False)

    def _toggle_details(self) -> None:
        showing = not self._details_view.isVisible()
        self._details_view.setVisible(showing)
        self._toggle.setText("Hide details" if showing else "Show details")
        self.adjustSize()

    def _copy_to_clipboard(self) -> None:
        QApplication.clipboard().setText(self._details)
        self._copy.setText("Copied")
        # snap back on next event loop tick
        from parallel_agents.desktop._qt import QTimer

        QTimer.singleShot(1200, lambda: self._copy.setText("Copy"))


def show_error(parent, title: str, message: str, details: str | None = None) -> None:
    dialog = ErrorDialog(parent, title, message, details)
    dialog.exec()
