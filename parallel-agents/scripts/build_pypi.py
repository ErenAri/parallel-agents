#!/usr/bin/env python3
"""Build and optionally publish to PyPI.

Usage:
    python scripts/build_pypi.py          # build only
    python scripts/build_pypi.py publish   # build + publish to PyPI
    python scripts/build_pypi.py test      # build + publish to TestPyPI
"""

import subprocess
import sys
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

def run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def clean_build_artifacts() -> None:
    shutil.rmtree(ROOT / "dist", ignore_errors=True)
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    for pattern in ("*.egg-info", "src/*.egg-info"):
        for path in ROOT.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.exists():
                path.unlink()


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "build"

    # Clean previous builds
    run([sys.executable, "-m", "pip", "install", "--upgrade", "build", "twine"])
    clean_build_artifacts()

    # Build
    run([sys.executable, "-m", "build"])

    dist_files = sorted((ROOT / "dist").glob("*"))
    if not dist_files:
        raise SystemExit("No distribution artifacts were generated in dist/")

    if action == "publish":
        run([sys.executable, "-m", "twine", "upload", *[str(p) for p in dist_files]])
    elif action == "test":
        run(
            [
                sys.executable,
                "-m",
                "twine",
                "upload",
                "--repository",
                "testpypi",
                *[str(p) for p in dist_files],
            ]
        )
    else:
        print("\nBuilt successfully! Artifacts in dist/")
        print("  To publish: python scripts/build_pypi.py publish")
        print("  To test:    python scripts/build_pypi.py test")


if __name__ == "__main__":
    main()
