from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from parallel_agents.project_office import (
    init_project_office,
    resolve_project_root,
    run_office_diagnostics,
    run_office_setup_fix,
)


def build_onboarding_report(
    project_root: str | Path | None = None,
    *,
    name: str | None = None,
    fix_setup: bool = True,
    check_github_auth: bool = True,
) -> dict[str, Any]:
    """Prepare a project for the first local office run and report readiness.

    The report is intentionally deterministic and safe: it only creates/repairs
    the local `.parallel-agents` workspace when `fix_setup` is true. It never
    starts an LLM run or performs remote GitHub writes.
    """
    root = resolve_project_root(project_root)
    before = run_office_diagnostics(root)
    actions_taken: list[str] = []

    if fix_setup:
        if name:
            init_project_office(root, name=name)
            actions_taken.append("initialized_or_updated_office_workspace")
        else:
            setup_result = run_office_setup_fix(root)
            actions_taken.extend(list(setup_result.get("actions_taken") or []))
    elif name and bool(before.get("office_initialized")):
        init_project_office(root, name=name)
        actions_taken.append("updated_project_name")

    after = run_office_diagnostics(root)
    llm = _llm_readiness()
    github = _github_readiness(check_auth=check_github_auth)
    blocking_failures = _blocking_failures(after)

    ready_for_local_run = not blocking_failures and llm["status"] == "passed"
    ready_for_github_flow = ready_for_local_run and github["status"] == "passed"
    status = (
        "ready"
        if ready_for_github_flow
        else "needs_github_auth"
        if ready_for_local_run
        else "needs_model_auth"
        if not blocking_failures and llm["status"] != "passed"
        else "blocked"
    )

    return {
        "status": status,
        "project_root": str(root),
        "before": before,
        "after": after,
        "actions_taken": actions_taken,
        "blocking_failures": blocking_failures,
        "llm": llm,
        "github": github,
        "ready_for_local_run": ready_for_local_run,
        "ready_for_github_flow": ready_for_github_flow,
        "next_actions": _next_actions(
            root,
            blocking_failures=blocking_failures,
            llm=llm,
            github=github,
        ),
    }


def _blocking_failures(diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for check in diagnostics.get("checks", []):
        if not isinstance(check, dict):
            continue
        if str(check.get("status")) != "failed":
            continue
        name = str(check.get("name") or "")
        if bool(check.get("required")) or name in {
            "project-root",
            "office-initialized",
            "workspace-directories",
        }:
            blockers.append(check)
    return blockers


def _llm_readiness() -> dict[str, Any]:
    env_keys = [
        key
        for key in ("ANTHROPIC_API_KEY", "PA_ANTHROPIC_API_KEY")
        if os.environ.get(key)
    ]
    claude_path = shutil.which("claude")
    if env_keys or claude_path:
        detail_parts = []
        if env_keys:
            detail_parts.append(f"env: {', '.join(env_keys)}")
        if claude_path:
            detail_parts.append(f"claude: {claude_path}")
        return {
            "status": "passed",
            "detail": "; ".join(detail_parts),
            "auth_modes": ["env"] if env_keys else [],
            "claude_cli": claude_path,
        }
    return {
        "status": "warning",
        "detail": "No ANTHROPIC_API_KEY/PA_ANTHROPIC_API_KEY or Claude CLI found.",
        "auth_modes": [],
        "claude_cli": None,
    }


def _github_readiness(*, check_auth: bool) -> dict[str, Any]:
    gh_path = shutil.which("gh")
    if not gh_path:
        return {
            "status": "warning",
            "detail": "GitHub CLI not found; GitHub issue/PR flow is unavailable.",
            "gh_path": None,
            "authenticated": False,
        }
    if not check_auth:
        return {
            "status": "warning",
            "detail": "GitHub CLI found; auth status was not checked.",
            "gh_path": gh_path,
            "authenticated": False,
        }

    try:
        proc = subprocess.run(
            [gh_path, "auth", "status"],
            text=True,
            capture_output=True,
            timeout=8,
        )
    except Exception as exc:  # noqa: BLE001 - readiness must degrade cleanly
        return {
            "status": "warning",
            "detail": f"GitHub auth status check failed: {exc}",
            "gh_path": gh_path,
            "authenticated": False,
        }

    output = "\n".join(part for part in [proc.stdout, proc.stderr] if part).strip()
    return {
        "status": "passed" if proc.returncode == 0 else "warning",
        "detail": _truncate(output or "gh auth status returned no output"),
        "gh_path": gh_path,
        "authenticated": proc.returncode == 0,
    }


def _next_actions(
    root: Path,
    *,
    blocking_failures: list[dict[str, Any]],
    llm: dict[str, Any],
    github: dict[str, Any],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if blocking_failures:
        actions.append(
            {
                "label": "Fix local blockers",
                "command": f"parallel-agents office fix-setup --project {_quote(root)} --strict",
            }
        )
    if llm.get("status") != "passed":
        actions.append(
            {
                "label": "Configure model auth",
                "command": "claude --version  # then authenticate Claude Code, or set ANTHROPIC_API_KEY",
            }
        )
    if github.get("status") != "passed":
        actions.append(
            {
                "label": "Connect GitHub",
                "command": "gh auth login",
            }
        )
    actions.extend(
        [
            {
                "label": "Run first safe analysis",
                "command": (
                    f"parallel-agents run --repo {_quote(root)} "
                    '"Review this project and propose a small safe PR"'
                ),
            },
            {
                "label": "Open desktop office",
                "command": "parallel-agents-desktop",
            },
            {
                "label": "Start local gateway",
                "command": f"parallel-agents gateway start --output-dir {_quote(root / '.parallel-agents')}",
            },
        ]
    )
    return actions


def _quote(path: Path) -> str:
    text = str(path)
    if any(ch.isspace() for ch in text):
        return f'"{text}"'
    return text


def _truncate(value: str, limit: int = 600) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."
