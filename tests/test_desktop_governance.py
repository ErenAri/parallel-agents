"""Tests for Phase 3 governance: hash-chained audit, content-digest binding,
supersede-on-regenerate, path-traversal sanitization, and chain verification."""

from __future__ import annotations

import json

import pytest

from parallel_agents.company_artifacts import (
    append_company_artifact_event,
    append_hash_chained_line,
    load_company_artifact_events,
    persist_company_artifact,
    verify_company_artifact_chain,
    verify_hash_chain,
    verify_run_audit_chains,
)
from parallel_agents.desktop.services.engine import EngineService


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def _new_engine(tmp_path):
    eng = EngineService()
    eng.init_project(str(tmp_path), name="Gov")
    return eng


# -- path traversal -----------------------------------------------------------

def test_persist_rejects_traversal_run_id(tmp_path):
    with pytest.raises(ValueError):
        persist_company_artifact(tmp_path, "../../escape", "brief", {"x": 1})


def test_append_event_rejects_traversal_artifact_name(tmp_path):
    with pytest.raises(ValueError):
        append_company_artifact_event(tmp_path, "run-1", "../../evil", {"event": "x"})


def test_read_side_rejects_traversal_run_id(tmp_path):
    # Read paths must sanitize too — they are reachable from HTTP payloads.
    with pytest.raises(ValueError):
        load_company_artifact_events(tmp_path, "../../escape", "issue-plan")


@pytest.mark.parametrize("name", ["CON", "nul", "COM1", "LPT9", "aux.json"])
def test_rejects_windows_reserved_device_names(tmp_path, name):
    with pytest.raises(ValueError):
        persist_company_artifact(tmp_path, name, "brief", {"x": 1})


# -- HMAC keying + sequence binding ------------------------------------------

def test_hmac_keying_detects_full_rewrite(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_AUDIT_HMAC_KEY", "s3cret-verifier-key")
    log = tmp_path / "events.jsonl"
    append_hash_chained_line(log, {"event": "a"})
    append_hash_chained_line(log, {"event": "b"})
    assert verify_hash_chain(log).ok

    # An attacker without the key forges entry 0 and recomputes the *unkeyed*
    # chain. With the key configured, verification still rejects it.
    from parallel_agents.company_artifacts import _compute_entry_hash

    monkeypatch.delenv("PA_AUDIT_HMAC_KEY", raising=False)
    forged_payload = {"event": "forged"}
    forged_hash = _compute_entry_hash(0, "2099-01-01T00:00:00+00:00", forged_payload, None)
    log.write_text(
        json.dumps(
            {
                "seq": 0,
                "timestamp": "2099-01-01T00:00:00+00:00",
                "hash": forged_hash,
                "previous_hash": None,
                "payload": forged_payload,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PA_AUDIT_HMAC_KEY", "s3cret-verifier-key")
    assert not verify_hash_chain(log).ok


def test_inserted_entry_breaks_sequence(tmp_path):
    log = tmp_path / "events.jsonl"
    e0 = append_hash_chained_line(log, {"event": "a"})
    append_hash_chained_line(log, {"event": "b"})

    # Re-insert entry 0 a second time: linkage looks fine but seq repeats.
    lines = log.read_text(encoding="utf-8").splitlines()
    lines.insert(1, json.dumps(e0))
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_hash_chain(log)
    assert not result.ok


def test_append_refuses_on_broken_chain(tmp_path):
    log = tmp_path / "events.jsonl"
    append_hash_chained_line(log, {"event": "a"})
    # Corrupt the only entry, then try to append: must refuse, not silently chain.
    entry = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    entry["payload"]["event"] = "TAMPERED"
    log.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="broken audit chain"):
        append_hash_chained_line(log, {"event": "b"})


def test_broken_index_is_logical_with_leading_blank_line(tmp_path):
    log = tmp_path / "events.jsonl"
    append_hash_chained_line(log, {"event": "a"})
    append_hash_chained_line(log, {"event": "b"})
    lines = log.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[1])
    entry["payload"]["event"] = "TAMPERED"
    lines[1] = json.dumps(entry)
    # blank line up front must not shift the reported logical index
    log.write_text("\n" + "\n".join(lines) + "\n", encoding="utf-8")

    result = verify_hash_chain(log)
    assert not result.ok
    assert result.broken_index == 1


def test_apply_fails_closed_when_digest_missing(tmp_path):
    eng = _new_engine(tmp_path)
    brief = eng.create_brief("an idea", title="T")
    eng.create_roadmap(brief.run_id)
    eng.create_issue_plan(brief.run_id, "acme/demo")
    approval = next(
        e for e in eng.list_pending_approvals() if e["data"]["artifact"] == "issue-plan"
    )
    # Strip the bound digest to simulate a legacy/missing-file approval.
    from pathlib import Path

    apath = Path(approval["path"])
    data = json.loads(apath.read_text(encoding="utf-8"))
    data["artifact_sha256"] = None
    data["status"] = "approved"
    apath.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PermissionError, match="no bound artifact digest"):
        eng.apply_issue_plan(brief.run_id, dry_run=True)


# -- hash chain + timestamp coverage -----------------------------------------

def test_chain_verifies_and_detects_payload_tamper(tmp_path):
    persist_company_artifact(tmp_path, "run-1", "brief", {"id": "b"})
    append_company_artifact_event(tmp_path, "run-1", "brief", {"event": "created"})
    append_company_artifact_event(tmp_path, "run-1", "brief", {"event": "approved"})

    assert verify_company_artifact_chain(tmp_path, "run-1", "brief").ok

    log = tmp_path / "run-1" / "company" / "audit" / "brief.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[1])
    entry["payload"]["event"] = "TAMPERED"  # change content, keep old hash
    lines[1] = json.dumps(entry)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = verify_company_artifact_chain(tmp_path, "run-1", "brief")
    assert not result.ok
    assert result.reason == "hash-mismatch"


def test_chain_detects_timestamp_backdating(tmp_path):
    persist_company_artifact(tmp_path, "run-2", "brief", {"id": "b"})
    append_company_artifact_event(tmp_path, "run-2", "brief", {"event": "created"})

    log = tmp_path / "run-2" / "company" / "audit" / "brief.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["timestamp"] = "1999-01-01T00:00:00+00:00"  # backdate without rehashing
    lines[0] = json.dumps(entry)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # timestamp is inside the hashed body, so backdating breaks the chain
    assert not verify_company_artifact_chain(tmp_path, "run-2", "brief").ok


# -- governance log is chained ------------------------------------------------

def test_governance_log_is_hash_chained(tmp_path):
    from parallel_agents.project_office import office_dir

    eng = _new_engine(tmp_path)
    brief = eng.create_brief("an idea", title="T")
    eng.create_roadmap(brief.run_id)

    log = office_dir(tmp_path) / "audit" / "events.jsonl"
    chain = verify_hash_chain(log, "governance-log")
    assert chain.ok and chain.entry_count >= 1

    # entries carry chained metadata, not a bare event dict
    first = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert {"timestamp", "hash", "previous_hash", "payload"} <= set(first)
    assert first["payload"]["event"] == "approval.created"


def test_verify_audit_chains_reports_ok_and_detects_break(tmp_path):
    from parallel_agents.project_office import office_dir

    eng = _new_engine(tmp_path)
    eng.create_brief("an idea", title="T")
    assert eng.verify_audit_chains()["ok"] is True

    log = office_dir(tmp_path) / "audit" / "events.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["payload"]["event"] = "forged"
    lines[0] = json.dumps(entry)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = eng.verify_audit_chains()
    assert report["ok"] is False
    assert report["governance_log"]["ok"] is False


# -- content-digest binding (approve-then-swap TOCTOU) -----------------------

def test_apply_refuses_when_plan_changed_after_approval(tmp_path):
    eng = _new_engine(tmp_path)
    brief = eng.create_brief("an idea", title="T")
    eng.create_roadmap(brief.run_id)
    eng.create_issue_plan(brief.run_id, "acme/demo")

    approval = next(
        e for e in eng.list_pending_approvals() if e["data"]["artifact"] == "issue-plan"
    )
    assert approval["data"].get("artifact_sha256")  # digest was recorded
    eng.approve(approval["path"], approver="lead")

    # Tamper with the approved artifact bytes after approval.
    from parallel_agents.project_office import office_output_dir

    plan_path = office_output_dir(tmp_path) / brief.run_id / "company" / "issue-plan.json"
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    data["issues"].append({"title": "sneaky injected issue", "milestone": "M1"})
    plan_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(PermissionError, match="changed since approval"):
        eng.apply_issue_plan(brief.run_id, dry_run=True)


def test_apply_succeeds_when_unchanged(tmp_path):
    eng = _new_engine(tmp_path)
    brief = eng.create_brief("an idea", title="T")
    eng.create_roadmap(brief.run_id)
    eng.create_issue_plan(brief.run_id, "acme/demo")
    approval = next(
        e for e in eng.list_pending_approvals() if e["data"]["artifact"] == "issue-plan"
    )
    eng.approve(approval["path"], approver="lead")
    result = eng.apply_issue_plan(brief.run_id, dry_run=True)
    assert result["mode"] == "dry-run"


# -- supersede on regenerate --------------------------------------------------

def test_regenerate_after_decision_records_supersede(tmp_path):
    eng = _new_engine(tmp_path)
    brief = eng.create_brief("an idea", title="T")
    eng.create_roadmap(brief.run_id)
    eng.create_issue_plan(brief.run_id, "acme/demo")
    approval = next(
        e for e in eng.list_pending_approvals() if e["data"]["artifact"] == "issue-plan"
    )
    eng.approve(approval["path"], approver="lead")

    # Regenerate the issue plan -> the prior approved decision is superseded.
    eng.create_issue_plan(brief.run_id, "acme/demo")

    events = eng.list_audit_events(run_id=brief.run_id, limit=0)
    superseded = [e for e in events if e.get("event") == "approval.superseded"]
    assert superseded and superseded[0]["previous_status"] == "approved"

    # and the fresh approval is pending again (decision was not silently kept)
    refreshed = next(
        e for e in eng.list_all_approvals() if e["data"]["artifact"] == "issue-plan"
    )
    assert refreshed["data"]["status"] == "pending"


# -- run-level verification helper -------------------------------------------

def test_verify_run_audit_chains_aggregates(tmp_path):
    eng = _new_engine(tmp_path)
    brief = eng.create_brief("an idea", title="T")
    eng.create_roadmap(brief.run_id)
    from parallel_agents.project_office import office_output_dir

    report = verify_run_audit_chains(office_output_dir(tmp_path), brief.run_id)
    assert report.ok
    assert {c.artifact_name for c in report.chains} >= {"brief", "roadmap"}
