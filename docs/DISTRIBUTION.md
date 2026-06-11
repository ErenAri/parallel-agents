# Distribution & Packaging

How the Parallel Agents artifacts are built, smoke-tested, and shipped — and the
prep work still required before the desktop installer is consumer-ready
(code signing, auto-update, winget).

## Artifacts

| Artifact | Built by | Output |
| --- | --- | --- |
| Python package (PyPI) | `python -m build` | wheel + sdist |
| npm wrapper | `npm publish` | `npm-wrapper/` |
| CLI binary (3 OSes) | `pyinstaller parallel-agents.spec` | single executable |
| Desktop app (3 OSes) | `pyinstaller parallel-agents-desktop.spec` | **onedir** bundle |
| Windows installer | Inno Setup (`installer/parallel-agents-desktop.iss`) | `*-setup-*.exe` |

The desktop app is built **onedir** (a launcher plus its unpacked Qt runtime)
rather than onefile: it starts faster, is far easier to code-sign (you sign the
files in place), and is what the Inno Setup installer packages.

## CI gates

- **`ci.yml` → `test`** runs the full pytest suite on Linux/macOS/Windows ×
  Python 3.11–3.13. The desktop smoke *scripts* run here too (they use a Qt
  stub, so they need no PySide6).
- **`ci.yml` → `desktop`** installs the real PySide6 and runs
  `tests/test_desktop_smoke.py` under an offscreen Qt platform on Linux and
  Windows. This exercises the real Qt stack, including a headless launch of the
  full window via `parallel-agents-desktop --smoke`.
- **`release.yml` → `desktop`** builds the onedir bundle on all three OSes,
  **smoke-executes the built binary** (`--smoke` under offscreen Qt) so a broken
  package fails the release, and builds the Windows installer.

### The `--smoke` flag

`parallel-agents-desktop --smoke` (or `PA_DESKTOP_SMOKE=1`) builds the entire
main window, starts and immediately stops the Qt event loop, and exits `0`. It
is the single mechanism behind both the pytest-qt offscreen test and the CI
binary smoke-execute, so "it imports" and "it actually launches packaged" are
both gated, not assumed.

## Still required before consumer GA

These are intentionally **not** wired up yet; this section is the runbook.

### 1. Code signing

Unsigned binaries trip SmartScreen (Windows) and Gatekeeper (macOS).

- **Windows**: sign `dist/parallel-agents-desktop/*.exe` *and* the final
  installer with `signtool` using an EV/OV certificate (ideally an Azure Trusted
  Signing or HSM-backed key, never a PEM in the repo). Add a signing step after
  the PyInstaller build and after `ISCC.exe`. Store the cert in
  `secrets.WINDOWS_CODE_SIGN_*`.
- **macOS**: `codesign --deep --options runtime` the `.app`/bundle with a
  Developer ID cert, then `notarytool submit --wait` and `stapler staple`. The
  spec's `codesign_identity`/`entitlements_file` fields are the hooks for this.

### 2. Auto-update (tufup)

Ship updates without users re-downloading installers.

- Adopt [`tufup`](https://github.com/dennisvang/tufup): maintain a TUF repository
  of desktop archives, embed a `tufup.client.Client` check on startup (behind a
  setting), and host the metadata + targets on a CDN.
- Generate and **offline-store** the TUF root/targets keys; the release job only
  needs the targets-signing key. Bump the bundle version on each release so the
  client can resolve a newer target.

### 3. winget

- Add a `manifests/` entry (installer + locale + version YAML) pointing at the
  signed installer's release URL and its SHA256.
- Automate submission to `microsoft/winget-pkgs` via
  [`winget-create`](https://github.com/microsoft/winget-create) (`wingetcreate
  update`) as a release step, gated on the installer being **signed** (winget
  validation rejects unsigned installers that trigger SmartScreen).

## Local build

```bash
pip install -e ".[desktop]" pyinstaller
pyinstaller --noconfirm parallel-agents-desktop.spec
# Windows installer (needs Inno Setup 6):
iscc installer\parallel-agents-desktop.iss
```
