# PyInstaller spec for the Parallel Agents Office desktop binary (PySide6).
#
# Prereq: pip install parallel-agents[desktop]  (installs PySide6)
# Build:  pyinstaller parallel-agents-desktop.spec
# Output: dist/parallel-agents-desktop[.exe]
#
# Produces a windowed binary (no console). For the headless CLI binary,
# use parallel-agents.spec instead.

from pathlib import Path

block_cipher = None
src_path = Path("src")

a = Analysis(
    [str(src_path / "parallel_agents" / "desktop" / "__main__.py")],
    pathex=[str(src_path)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # engine modules the desktop UI calls into
        "parallel_agents",
        "parallel_agents.models",
        "parallel_agents.config",
        "parallel_agents.pipeline",
        "parallel_agents.evidence_store",
        "parallel_agents.cost_tracker",
        "parallel_agents.project_office",
        "parallel_agents.company_artifacts",
        "parallel_agents.company_policy",
        "parallel_agents.company_workflows",
        "parallel_agents.tools",
        "parallel_agents.tools.github_tools",
        "parallel_agents.tools.github_apply",
        # desktop tree
        "parallel_agents.desktop",
        "parallel_agents.desktop.app",
        "parallel_agents.desktop.main_window",
        "parallel_agents.desktop.theme",
        "parallel_agents.desktop.widgets",
        "parallel_agents.desktop.widgets.sidebar",
        "parallel_agents.desktop.widgets.worker_grid",
        "parallel_agents.desktop.widgets.artifact_viewer",
        "parallel_agents.desktop.services",
        "parallel_agents.desktop.services.engine",
        "parallel_agents.desktop.services.workers",
        "parallel_agents.desktop.services.llm",
        "parallel_agents.desktop.services.llm_brief",
        "parallel_agents.desktop.services.llm_prfaq",
        "parallel_agents.desktop.services.llm_rfc",
        "parallel_agents.desktop.pages",
        "parallel_agents.desktop.pages._base",
        "parallel_agents.desktop.pages.projects_page",
        "parallel_agents.desktop.pages.company_page",
        "parallel_agents.desktop.pages.runs_page",
        "parallel_agents.desktop.pages.approvals_page",
        "parallel_agents.desktop.pages.artifacts_page",
        "parallel_agents.desktop.pages.settings_page",
        # third-party
        "pydantic",
        "pydantic_settings",
        "anthropic",
        # PySide6 — PyInstaller usually picks these up via its hook,
        # listed explicitly for clarity and to fail fast on missing extra.
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="parallel-agents-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # windowed app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
