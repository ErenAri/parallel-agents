# PyInstaller spec file for parallel-agents standalone binary
# Usage: pyinstaller parallel-agents.spec

import sys
from pathlib import Path

block_cipher = None
src_path = Path("src")

a = Analysis(
    [str(src_path / "parallel_agents" / "main.py")],
    pathex=[str(src_path)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "parallel_agents",
        "parallel_agents.models",
        "parallel_agents.config",
        "parallel_agents.pipeline",
        "parallel_agents.evidence_store",
        "parallel_agents.cost_tracker",
        "parallel_agents.agents",
        "parallel_agents.agents.base",
        "parallel_agents.agents.planner",
        "parallel_agents.agents.splitter",
        "parallel_agents.agents.judge",
        "parallel_agents.agents.workers",
        "parallel_agents.agents.workers.security",
        "parallel_agents.agents.workers.code",
        "parallel_agents.agents.workers.review",
        "parallel_agents.agents.workers.test",
        "parallel_agents.agents.workers.perf",
        "parallel_agents.agents.workers.devops",
        "parallel_agents.agents.workers.arch",
        "parallel_agents.agents.workers.docs",
        "parallel_agents.tools",
        "parallel_agents.tools.evidence_tools",
        "parallel_agents.tools.github_tools",
        "click",
        "rich",
        "pydantic",
        "pydantic_settings",
        "claude_code_sdk",
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
    name="parallel-agents",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
