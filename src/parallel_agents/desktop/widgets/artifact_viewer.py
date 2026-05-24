from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from parallel_agents.desktop._qt import QTextBrowser


class ArtifactViewer(QTextBrowser):
    def __init__(self) -> None:
        super().__init__()
        self.setOpenExternalLinks(True)
        self.setPlaceholderText("Select an artifact to preview")

    def show_path(self, path: Path) -> None:
        if not path.exists():
            self.setPlainText(f"Missing: {path}")
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(text)
                text = json.dumps(data, indent=2)
            except json.JSONDecodeError:
                pass
        if path.suffix.lower() in {".md", ".markdown"}:
            self.setMarkdown(text)
        else:
            self.setPlainText(text)

    def show_data(self, data: Any) -> None:
        self.setPlainText(json.dumps(data, indent=2, default=str))
