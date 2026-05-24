#!/usr/bin/env python3
"""Build standalone binaries using PyInstaller.

Usage:
    python scripts/build_binary.py              # build for current platform
    python scripts/build_binary.py --onedir     # build as directory

Output:
    dist/parallel-agents       (Linux/macOS)
    dist/parallel-agents.exe   (Windows)
"""

from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)


def main() -> None:
    onedir = "--onedir" in sys.argv

    run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])

    if onedir:
        run(
            [
                "pyinstaller",
                "--name",
                "parallel-agents",
                "--paths",
                "src",
                "--hidden-import",
                "parallel_agents",
                "--hidden-import",
                "parallel_agents.agents.workers.security",
                "--hidden-import",
                "parallel_agents.agents.workers.code",
                "--hidden-import",
                "parallel_agents.agents.workers.review",
                "--hidden-import",
                "parallel_agents.agents.workers.test",
                "--hidden-import",
                "parallel_agents.agents.workers.perf",
                "--hidden-import",
                "parallel_agents.agents.workers.devops",
                "--hidden-import",
                "parallel_agents.agents.workers.arch",
                "--hidden-import",
                "parallel_agents.agents.workers.docs",
                "--hidden-import",
                "click",
                "--hidden-import",
                "rich",
                "--hidden-import",
                "pydantic",
                "--hidden-import",
                "pydantic_settings",
                "--hidden-import",
                "claude_code_sdk",
                "--console",
                "--noconfirm",
                "src/parallel_agents/main.py",
            ]
        )
    else:
        run(["pyinstaller", "--noconfirm", "parallel-agents.spec"])

    system = platform.system().lower()
    ext = ".exe" if system == "windows" else ""
    binary = f"dist/parallel-agents{ext}"

    print(f"\nOK Binary built: {binary}")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Test: {binary} workers")


if __name__ == "__main__":
    main()

