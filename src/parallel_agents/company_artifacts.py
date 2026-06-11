from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Path segments that come from callers (including, on the gateway, attacker-
# influenced HTTP payloads) must not be able to escape the run directory.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Windows resolves these names to devices regardless of directory or extension
# (e.g. NUL.json silently discards writes, CON targets the console). Reject them
# everywhere so behaviour does not diverge between platforms.
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _safe_segment(value: str, kind: str) -> str:
    """Validate a single path segment (run_id, artifact_name).

    Rejects empties, '.'/'..', path separators, Windows reserved device names,
    and anything outside a strict allow-list so a value like '../../escape'
    cannot traverse out of the run directory.
    """
    cleaned = (value or "").strip()
    if cleaned in ("", ".", "..") or not _SAFE_SEGMENT.match(cleaned):
        raise ValueError(f"Invalid {kind}: {value!r}")
    if cleaned.split(".", 1)[0].upper() in _WIN_RESERVED:
        raise ValueError(f"Invalid {kind} (reserved device name): {value!r}")
    return cleaned


class CompanyArtifactIndex(BaseModel):
    run_id: str
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    artifacts: dict[str, str] = Field(default_factory=dict)


def persist_company_artifact(
    output_dir: str | Path,
    run_id: str,
    artifact_name: str,
    artifact_payload: BaseModel | dict[str, Any],
) -> Path:
    """Persist a company artifact under <output_dir>/<run_id>/company."""
    run_id = _safe_segment(run_id, "run_id")
    artifact_name = _safe_segment(artifact_name, "artifact_name")

    base = Path(output_dir) / run_id / "company"
    base.mkdir(parents=True, exist_ok=True)

    file_path = base / f"{artifact_name}.json"
    payload = _to_payload_dict(artifact_payload)
    file_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    index = load_company_artifact_index(output_dir, run_id) or CompanyArtifactIndex(run_id=run_id)
    index.artifacts[artifact_name] = file_path.name
    index.updated_at = _utc_now()
    (base / "index.json").write_text(index.model_dump_json(indent=2), encoding="utf-8")
    return file_path


def load_company_artifact_index(output_dir: str | Path, run_id: str) -> CompanyArtifactIndex | None:
    run_id = _safe_segment(run_id, "run_id")
    path = Path(output_dir) / run_id / "company" / "index.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return CompanyArtifactIndex.model_validate(payload)


def list_company_artifact_paths(output_dir: str | Path, run_id: str) -> dict[str, str]:
    run_id = _safe_segment(run_id, "run_id")
    index = load_company_artifact_index(output_dir, run_id)
    if not index:
        return {}
    base = Path(output_dir) / run_id / "company"
    return {name: str((base / rel_path).resolve()) for name, rel_path in index.artifacts.items()}


def load_company_artifact(
    output_dir: str | Path,
    run_id: str,
    artifact_name: str,
) -> dict[str, Any] | None:
    """Load one named artifact from a run-linked company artifact directory."""
    run_id = _safe_segment(run_id, "run_id")
    paths = list_company_artifact_paths(output_dir, run_id)
    artifact_path = paths.get(artifact_name)
    if not artifact_path:
        return None
    path = Path(artifact_path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def append_company_artifact_event(
    output_dir: str | Path,
    run_id: str,
    artifact_name: str,
    event_payload: BaseModel | dict[str, Any],
) -> Path:
    """Append an immutable event record for a company artifact."""
    run_id = _safe_segment(run_id, "run_id")
    artifact_name = _safe_segment(artifact_name, "artifact_name")

    base = Path(output_dir) / run_id / "company"
    audit_dir = base / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    log_path = audit_dir / f"{artifact_name}.jsonl"
    append_hash_chained_line(log_path, _to_payload_dict(event_payload))

    index = load_company_artifact_index(output_dir, run_id) or CompanyArtifactIndex(run_id=run_id)
    index.artifacts[f"{artifact_name}-audit-log"] = str(Path("audit") / log_path.name)
    index.updated_at = _utc_now()
    (base / "index.json").write_text(index.model_dump_json(indent=2), encoding="utf-8")
    return log_path


def load_company_artifact_events(
    output_dir: str | Path,
    run_id: str,
    artifact_name: str,
) -> list[dict[str, Any]]:
    """Load append-only event records for a company artifact."""
    run_id = _safe_segment(run_id, "run_id")
    artifact_name = _safe_segment(artifact_name, "artifact_name")
    log_path = Path(output_dir) / run_id / "company" / "audit" / f"{artifact_name}.jsonl"
    if not log_path.exists():
        return []

    events: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def _audit_key() -> bytes | None:
    """Return the optional HMAC key for the audit chain, if configured.

    When ``PA_AUDIT_HMAC_KEY`` is set the chain digest is HMAC-SHA256 keyed with
    a secret the log writer is assumed not to know (held by a separate verifier),
    which makes edits/insertions forgeable only by a holder of the key. Without
    it the chain is an unkeyed SHA-256 chain (integrity against accidental
    corruption and naive in-place edits only).
    """
    key = os.environ.get("PA_AUDIT_HMAC_KEY")
    return key.encode("utf-8") if key else None


def _compute_entry_hash(
    seq: int, timestamp: str, payload: dict[str, Any], previous_hash: str | None
) -> str:
    body = {
        "seq": seq,
        "timestamp": timestamp,
        "payload": payload,
        "previous_hash": previous_hash,
    }
    body_json = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    encoded = body_json.encode("utf-8")
    key = _audit_key()
    if key:
        return hmac.new(key, encoded, hashlib.sha256).hexdigest()
    return hashlib.sha256(encoded).hexdigest()


def append_hash_chained_line(log_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Append one hash-chained entry to a .jsonl log.

    Shared by the per-artifact audit log and the workspace-wide governance log.
    Each entry binds its sequence number, timestamp, payload, and the previous
    entry's hash, so an in-place edit, insertion, or reordering breaks the chain.

    Threat model and limits (kept honest deliberately):
      - Without ``PA_AUDIT_HMAC_KEY`` the digest is an unkeyed SHA-256 chain: it
        detects accidental corruption and naive edits, but an attacker who can
        rewrite the whole file can recompute every hash. Set the env var to a
        secret held outside the writer to get HMAC-SHA256 and real
        tamper-evidence against edits/insertions.
      - Truncation of the most recent entries cannot be detected from the log
        alone (a shorter prefix is still self-consistent). Verify regularly and,
        for high-assurance use, anchor the head hash + count externally.

    Before appending, the existing chain is verified; appending onto a broken or
    forged tail is refused so the append and verify paths never disagree.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = verify_hash_chain(log_path)
    if not existing.ok:
        raise RuntimeError(
            f"refusing to append to broken audit chain {log_path.name}: {existing.reason}"
        )
    previous_hash, seq = _load_chain_tail(log_path)
    timestamp = _utc_now().isoformat()
    entry = {
        "seq": seq,
        "timestamp": timestamp,
        "hash": _compute_entry_hash(seq, timestamp, payload, previous_hash),
        "previous_hash": previous_hash,
        "payload": payload,
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str))
        handle.write("\n")
    return entry


def verify_hash_chain(log_path: Path, label: str = "") -> ChainVerification:
    """Recompute a hash-chained .jsonl log and report the first break, if any.

    ``broken_index`` and ``entry_count`` both count logical entries (0-based),
    skipping blank lines, so they stay consistent across every break reason.
    """
    if not log_path.exists():
        return ChainVerification(label, True, 0, reason="no-log")

    expected_prev: str | None = None
    expected_seq = 0
    count = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            return ChainVerification(label, False, count, broken_index=count, reason="invalid-json")
        if entry.get("previous_hash") != expected_prev:
            return ChainVerification(label, False, count, broken_index=count, reason="broken-linkage")
        if entry.get("seq") != expected_seq:
            return ChainVerification(label, False, count, broken_index=count, reason="seq-gap")
        recomputed = _compute_entry_hash(
            expected_seq,
            str(entry.get("timestamp", "")),
            entry.get("payload", {}),
            entry.get("previous_hash"),
        )
        if recomputed != entry.get("hash"):
            return ChainVerification(label, False, count, broken_index=count, reason="hash-mismatch")
        expected_prev = entry.get("hash")
        expected_seq += 1
        count += 1

    return ChainVerification(label, True, count)


@dataclass
class ChainVerification:
    """Result of recomputing a single artifact's audit chain."""

    artifact_name: str
    ok: bool
    entry_count: int
    broken_index: int | None = None
    reason: str | None = None


@dataclass
class RunChainVerification:
    """Aggregate verification across every audit log in a run."""

    run_id: str
    ok: bool
    chains: list[ChainVerification] = field(default_factory=list)


def verify_company_artifact_chain(
    output_dir: str | Path,
    run_id: str,
    artifact_name: str,
) -> ChainVerification:
    """Recompute an artifact's hash chain and report the first break, if any.

    Recomputes every entry hash over (seq, timestamp, payload, previous_hash)
    and checks the previous_hash linkage and sequence ordering. See
    ``append_hash_chained_line`` for the exact tamper-evidence guarantees and
    their limits (HMAC keying, tail-truncation).
    """
    run_id = _safe_segment(run_id, "run_id")
    artifact_name = _safe_segment(artifact_name, "artifact_name")
    log_path = Path(output_dir) / run_id / "company" / "audit" / f"{artifact_name}.jsonl"
    return verify_hash_chain(log_path, artifact_name)


def verify_run_audit_chains(
    output_dir: str | Path, run_id: str
) -> RunChainVerification:
    """Verify every audit chain under a run's company directory."""
    run_id = _safe_segment(run_id, "run_id")
    audit_dir = Path(output_dir) / run_id / "company" / "audit"
    chains: list[ChainVerification] = []
    if audit_dir.is_dir():
        for log_path in sorted(audit_dir.glob("*.jsonl")):
            chains.append(
                verify_company_artifact_chain(output_dir, run_id, log_path.stem)
            )
    return RunChainVerification(
        run_id=run_id, ok=all(c.ok for c in chains), chains=chains
    )


def _load_chain_tail(log_path: Path) -> tuple[str | None, int]:
    """Return (last_hash, next_seq) for an already-verified chain.

    Callers must verify the chain first (``append_hash_chained_line`` does), so
    every line parses and sequence numbers are contiguous from 0 — next_seq is
    therefore the entry count.
    """
    if not log_path.exists():
        return None, 0
    last_hash: str | None = None
    seq = 0
    for line in log_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        entry = json.loads(stripped)
        value = entry.get("hash")
        if isinstance(value, str) and value:
            last_hash = value
        seq += 1
    return last_hash, seq


def _to_payload_dict(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value
