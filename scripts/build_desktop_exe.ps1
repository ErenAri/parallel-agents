#!/usr/bin/env pwsh
# Build the Parallel Agents Office desktop .exe with PyInstaller.
#
# Requires:
#   pip install -e ".[desktop,dev]"   # PySide6 + PyInstaller

$ErrorActionPreference = "Stop"

Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    Write-Host "Validating PySide6 is installed..."
    python -c "import PySide6" 2>$null
    if (-not $?) {
        Write-Error "PySide6 not installed. Run: pip install -e `".[desktop,dev]`""
    }

    Write-Host "Validating PyInstaller is installed..."
    python -c "import PyInstaller" 2>$null
    if (-not $?) {
        Write-Error "PyInstaller not installed. Run: pip install -e `".[dev]`""
    }

    Write-Host "Smoke-checking desktop imports..."
    python scripts/smoke_desktop_imports.py
    if (-not $?) { Write-Error "Import smoke test failed; aborting build." }

    Write-Host "Building parallel-agents-desktop..."
    pyinstaller --clean --noconfirm parallel-agents-desktop.spec
    if (-not $?) { Write-Error "PyInstaller build failed." }

    Write-Host ""
    Write-Host "Built: dist\parallel-agents-desktop.exe"
}
finally {
    Pop-Location
}
