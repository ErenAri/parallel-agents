#!/usr/bin/env python3
"""Build and optionally publish to PyPI.

Usage:
    python scripts/build_pypi.py          # build only
    python scripts/build_pypi.py publish   # build + publish to PyPI
    python scripts/build_pypi.py test      # build + publish to TestPyPI
"""

import subprocess
import sys


def run(cmd: str) -> None:
    print(f"$ {cmd}")
    subprocess.check_call(cmd, shell=True)


def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else "build"

    # Clean previous builds
    run("python -m pip install --upgrade build twine")
    run("rm -rf dist/ build/ *.egg-info src/*.egg-info")

    # Build
    run("python -m build")

    if action == "publish":
        run("python -m twine upload dist/*")
    elif action == "test":
        run("python -m twine upload --repository testpypi dist/*")
    else:
        print("\nBuilt successfully! Artifacts in dist/")
        print("  To publish: python scripts/build_pypi.py publish")
        print("  To test:    python scripts/build_pypi.py test")


if __name__ == "__main__":
    main()
