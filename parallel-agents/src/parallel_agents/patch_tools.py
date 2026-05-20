"""Patch validation and optional patch application helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path


def validate_unified_diff(patch: str) -> tuple[bool, str]:
    """Validate that text looks like a unified diff with at least one hunk."""
    if not patch or not patch.strip():
        return False, "Patch is empty."

    lines = patch.splitlines()
    seen_file_header = False
    seen_hunk = False
    expecting_new_file_header = False

    for line in lines:
        if line.startswith("--- "):
            expecting_new_file_header = True
            continue
        if line.startswith("+++ "):
            if not expecting_new_file_header:
                return False, "Patch has '+++' header without matching '---' header."
            seen_file_header = True
            expecting_new_file_header = False
            continue
        if line.startswith("@@ "):
            if not seen_file_header:
                return False, "Patch hunk encountered before file headers."
            seen_hunk = True

    if not seen_file_header:
        return False, "Patch missing file headers ('---'/'+++')."
    if not seen_hunk:
        return False, "Patch missing hunk markers ('@@')."
    return True, "Patch is a valid unified diff."


def apply_unified_diff(repo_path: str, patch: str) -> tuple[bool, str]:
    """Apply a validated unified diff to a git repository with pre-check."""
    valid, reason = validate_unified_diff(patch)
    if not valid:
        return False, reason

    path = Path(repo_path).resolve()
    if not path.exists() or not path.is_dir():
        return False, f"Repository path does not exist: {repo_path}"

    try:
        check_proc = subprocess.run(
            ["git", "-C", str(path), "apply", "--check", "-"],
            input=patch,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        return False, "git command not found."
    except OSError as exc:
        return False, f"Failed to run git apply --check: {exc}"

    if check_proc.returncode != 0:
        detail = (check_proc.stderr or check_proc.stdout).strip()
        return False, detail or "git apply --check failed."

    try:
        apply_proc = subprocess.run(
            ["git", "-C", str(path), "apply", "-"],
            input=patch,
            text=True,
            capture_output=True,
        )
    except OSError as exc:
        return False, f"Failed to run git apply: {exc}"

    if apply_proc.returncode != 0:
        detail = (apply_proc.stderr or apply_proc.stdout).strip()
        return False, detail or "git apply failed."
    return True, f"Patch applied to {path}"
