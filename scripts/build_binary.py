#!/usr/bin/env python3
"""Build standalone binary using PyInstaller.

Usage:
    python scripts/build_binary.py              # build for current platform
    python scripts/build_binary.py --onedir     # build as directory (faster builds)

Output:
    dist/parallel-agents       (Linux/macOS)
    dist/parallel-agents.exe   (Windows)
"""

import platform
import subprocess
import sys


def run(cmd: str) -> None:
    print(f"$ {cmd}")
    subprocess.check_call(cmd, shell=True)


def main() -> None:
    onedir = "--onedir" in sys.argv

    # Ensure PyInstaller is installed
    run("python -m pip install --upgrade pyinstaller")

    if onedir:
        # Faster build, produces a directory
        run(
            "pyinstaller "
            "--name parallel-agents "
            "--paths src "
            "--hidden-import parallel_agents "
            "--hidden-import parallel_agents.agents.workers.security "
            "--hidden-import parallel_agents.agents.workers.code "
            "--hidden-import parallel_agents.agents.workers.review "
            "--hidden-import parallel_agents.agents.workers.test "
            "--hidden-import parallel_agents.agents.workers.perf "
            "--hidden-import parallel_agents.agents.workers.devops "
            "--hidden-import parallel_agents.agents.workers.arch "
            "--hidden-import parallel_agents.agents.workers.docs "
            "--hidden-import click "
            "--hidden-import rich "
            "--hidden-import pydantic "
            "--hidden-import pydantic_settings "
            "--hidden-import claude_code_sdk "
            "--console "
            "--noconfirm "
            "src/parallel_agents/main.py"
        )
    else:
        # Single file binary
        run("pyinstaller --noconfirm parallel-agents.spec")

    system = platform.system().lower()
    ext = ".exe" if system == "windows" else ""
    binary = f"dist/parallel-agents{ext}"

    print(f"\n✓ Binary built: {binary}")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Test: {binary} workers")


if __name__ == "__main__":
    main()
