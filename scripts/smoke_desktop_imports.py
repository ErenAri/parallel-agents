"""Stub-PySide6 smoke test: validates that the desktop package imports cleanly
without requiring the real Qt runtime. Run from repo root:

    python scripts/smoke_desktop_imports.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path


def _install_pyside6_stub() -> None:
    class _StubMeta(type):
        # Resolve class-level enum access like QSizePolicy.Policy.Minimum or
        # QComboBox.InsertPolicy.NoInsert to nested stub instances.
        def __getattr__(cls, name):
            return _Stub()

    class _Stub(metaclass=_StubMeta):
        def __init__(self, *a, **kw):
            pass

        def __call__(self, *a, **kw):
            return self

        def __getattr__(self, name):
            return _Stub()

        def __setattr__(self, name, value):
            object.__setattr__(self, name, value)

        # Stubbed Qt accessors that return collections (selectedItems, findChildren,
        # etc.) should behave as empty iterables rather than blowing up.
        def __iter__(self):
            return iter(())

        def __len__(self):
            return 0

        def __bool__(self):
            return False

        # Stubbed int-returning accessors (count(), currentRow(), width(), ...).
        def __index__(self):
            return 0

        def __int__(self):
            return 0

        # Comparisons against ints (e.g. `if combo.findText(x) >= 0`) take the
        # not-found / falsy branch under the stub.
        def __lt__(self, other):
            return False

        def __le__(self, other):
            return False

        def __gt__(self, other):
            return False

        def __ge__(self, other):
            return False

    class _SignalStub:
        def __init__(self, *a, **kw):
            pass

        def __set_name__(self, owner, name):
            pass

        def __get__(self, instance, owner):
            return self

        def connect(self, *_a, **_kw):
            return None

        def emit(self, *_a, **_kw):
            return None

    class _EnumMember:
        def __init__(self, name): self._name = name
        def __repr__(self): return f"Stub({self._name})"
        def __getattr__(self, name): return _EnumMember(f"{self._name}.{name}")
        def __eq__(self, other): return isinstance(other, _EnumMember) and other._name == self._name
        def __hash__(self): return hash(self._name)
        # Qt enum/flag values support bitwise composition.
        def __invert__(self): return _EnumMember(f"~{self._name}")
        def __and__(self, other): return _EnumMember(f"{self._name}&")
        def __rand__(self, other): return _EnumMember(f"&{self._name}")
        def __or__(self, other): return _EnumMember(f"{self._name}|")
        def __ror__(self, other): return _EnumMember(f"|{self._name}")
        def __int__(self): return 0
        def __index__(self): return 0

    class _NamespaceMeta(type):
        def __getattr__(cls, item):
            return _EnumMember(item)

    class _Namespace(metaclass=_NamespaceMeta):
        pass

    def _make_module(name: str, attrs: dict) -> types.ModuleType:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
        return mod

    # QtCore
    qt_core = {
        "QObject": _Stub,
        "QSize": _Stub,
        "Qt": _Namespace,
        "QThread": _Stub,
        "QTimer": _Stub,
        "Signal": _SignalStub,
        "Slot": lambda *a, **kw: (lambda fn: fn),
    }
    # QtGui
    qt_gui = {n: _Stub for n in [
        "QAction", "QColor", "QFont", "QIcon", "QPainter", "QPalette",
        "QPen", "QPixmap", "QTextCharFormat", "QTextCursor",
    ]}
    # QtWidgets
    qt_widgets = {n: _Stub for n in [
        "QApplication", "QCheckBox", "QComboBox", "QDialog", "QDialogButtonBox",
        "QFileDialog", "QFormLayout", "QFrame", "QGridLayout",
        "QGroupBox", "QHBoxLayout", "QInputDialog", "QLabel", "QLineEdit",
        "QListWidget", "QListWidgetItem", "QMainWindow", "QMessageBox",
        "QPlainTextEdit", "QProgressBar", "QPushButton", "QScrollArea",
        "QSizePolicy", "QSpacerItem", "QSplitter", "QStackedWidget", "QStatusBar",
        "QStyle", "QTabWidget", "QTextBrowser", "QToolBar", "QTreeWidget",
        "QTreeWidgetItem", "QVBoxLayout", "QWidget",
    ]}

    pyside = types.ModuleType("PySide6")
    sys.modules["PySide6"] = pyside
    _make_module("PySide6.QtCore", qt_core)
    _make_module("PySide6.QtGui", qt_gui)
    _make_module("PySide6.QtWidgets", qt_widgets)


def main() -> int:
    repo_src = Path(__file__).resolve().parent.parent / "src"
    sys.path.insert(0, str(repo_src))
    _install_pyside6_stub()

    import importlib

    modules = [
        "parallel_agents.desktop",
        "parallel_agents.desktop._qt",
        "parallel_agents.desktop.theme",
        "parallel_agents.desktop.app",
        "parallel_agents.desktop.main_window",
        "parallel_agents.desktop.widgets.app_chrome",
        "parallel_agents.desktop.widgets.design_system",
        "parallel_agents.desktop.widgets.sidebar",
        "parallel_agents.desktop.widgets.worker_grid",
        "parallel_agents.desktop.widgets.artifact_viewer",
        "parallel_agents.desktop.services.engine",
        "parallel_agents.desktop.services.workers",
        "parallel_agents.desktop.services.llm",
        "parallel_agents.desktop.services.llm_config",
        "parallel_agents.desktop.services.llm_brief",
        "parallel_agents.desktop.services.llm_prfaq",
        "parallel_agents.desktop.services.llm_tech_stack",
        "parallel_agents.desktop.services.llm_rfc",
        "parallel_agents.desktop.services.llm_roadmap",
        "parallel_agents.desktop.services.llm_sprint",
        "parallel_agents.desktop.pages._base",
        "parallel_agents.desktop.pages.home_page",
        "parallel_agents.desktop.pages.projects_page",
        "parallel_agents.desktop.pages.company_page",
        "parallel_agents.desktop.pages.runs_page",
        "parallel_agents.desktop.pages.approvals_page",
        "parallel_agents.desktop.pages.artifacts_page",
        "parallel_agents.desktop.pages.settings_page",
    ]
    failed = []
    for name in modules:
        try:
            importlib.import_module(name)
            print(f"  ok  {name}")
        except Exception as exc:  # noqa: BLE001
            failed.append((name, exc))
            print(f" FAIL {name}: {type(exc).__name__}: {exc}")

    if failed:
        print(f"\n{len(failed)} import failure(s).")
        return 1
    print("\nAll desktop modules imported cleanly under the PySide6 stub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
