"""End-to-end engine smoke test (no Qt required).

Covers the full pipeline plus the follow-up additions:
  - LLM-flag fallback for brief, PR/FAQ, and RFC
  - Extracted github_apply module importable without dragging in click/CLI
  - apply_issue_plan remains gated on approval after the live-apply wiring
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    # Keep the smoke test hermetic: no live LLM calls regardless of environment.
    os.environ.pop("ANTHROPIC_API_KEY", None)
    from parallel_agents.desktop.services.engine import EngineService

    # --- Slice 1+2: full pipeline ---
    with tempfile.TemporaryDirectory() as tmp:
        eng = EngineService()
        info = eng.init_project(tmp, name="Smoke")
        print(f"project init: {info.name}")

        brief = eng.create_brief("Build a no-code AI software office", title="Demo")
        run_id = brief.run_id

        eng.create_prfaq(run_id)
        eng.create_tech_stack(run_id, repo_path=tmp)
        eng.create_rfc(run_id)
        eng.create_roadmap(run_id, horizon_weeks=8)
        eng.create_sprint(run_id, milestone="M1")
        eng.create_issue_plan(run_id, repo="acme/demo")
        print("pipeline 1-7: ok")

        # apply BEFORE approval blocked
        try:
            eng.apply_issue_plan(run_id, dry_run=True)
        except PermissionError:
            print("apply-before-approval still gated: ok")
        else:
            print("FAIL: apply succeeded without approval")
            return 1

        plan_approval = next(
            e for e in eng.list_pending_approvals()
            if e["data"]["artifact"] == "issue-plan"
        )
        eng.approve(plan_approval["path"], approver="eren", note="ship it")

        result = eng.apply_issue_plan(run_id, dry_run=True)
        assert result["mode"] == "dry-run"
        assert result["issues_planned"] >= 1
        print(f"apply dry-run via extracted executor: planned={result['issues_planned']}")

        # the extracted executor populated executor-shape fields too
        assert "milestones" in result
        assert "issues" in result
        assert all("status" in i for i in result["issues"])

        audit = Path(info.office_dir) / "audit" / "events.jsonl"
        events = [
            json.loads(line)
            for line in audit.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        applied = [e for e in events if e.get("event") == "issue-plan.apply"]
        assert len(applied) == 1 and applied[0]["mode"] == "dry-run"

    # --- FU-1: LLM-flag fallback for brief, PRFAQ, RFC ---
    # All three flags on, no API key -> all three must fall back deterministically.
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PA_DESKTOP_LLM_BRIEF"] = "1"
        os.environ["PA_DESKTOP_LLM_PRFAQ"] = "1"
        os.environ["PA_DESKTOP_LLM_RFC"] = "1"
        os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            eng = EngineService()
            eng.init_project(tmp, name="LLMFallback")
            brief = eng.create_brief("Fallback test idea", title="Fallback")
            brief_data = json.loads(brief.artifact_path.read_text(encoding="utf-8"))
            assert brief_data["title"] == "Fallback"
            assert "Solo builders" in brief_data["target_users"]

            prfaq = eng.create_prfaq(brief.run_id)
            prfaq_data = json.loads(prfaq.artifact_path.read_text(encoding="utf-8"))
            assert "Launches AI-Operated" in prfaq_data["headline"]

            stack = eng.create_tech_stack(brief.run_id, repo_path=tmp)
            assert stack.artifact_path.exists()
            rfc = eng.create_rfc(brief.run_id)
            rfc_data = json.loads(rfc.artifact_path.read_text(encoding="utf-8"))
            assert "Architecture RFC" in rfc_data["title"]
            print("LLM fallback for brief, prfaq, rfc: ok")
        finally:
            for k in ("PA_DESKTOP_LLM_BRIEF", "PA_DESKTOP_LLM_PRFAQ", "PA_DESKTOP_LLM_RFC"):
                os.environ.pop(k, None)

    # --- FU-2a: extracted module is self-contained (doesn't drag main.py / CLI in) ---
    # Fresh interpreter via subprocess for a clean import-graph check.
    import subprocess
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'src');"
            " import parallel_agents.tools.github_apply as g;"
            " assert hasattr(g, 'execute_company_issue_plan');"
            " assert 'parallel_agents.main' not in sys.modules,"
            " 'main.py leaked into github_apply import';"
            " print('github_apply self-contained: ok')",
        ],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
    )
    print(proc.stdout.strip() or proc.stderr.strip())
    assert proc.returncode == 0, f"subprocess failed: {proc.stderr}"

    print("\nOK: all follow-ups pass.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
