"""Tests for patch validation and application helpers."""

from __future__ import annotations

from types import SimpleNamespace

from parallel_agents.patch_tools import apply_unified_diff, validate_unified_diff


VALID_PATCH = """--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-old
+new
"""


def test_validate_unified_diff_accepts_valid_patch():
    valid, reason = validate_unified_diff(VALID_PATCH)
    assert valid is True
    assert "valid unified diff" in reason.lower()


def test_validate_unified_diff_rejects_missing_headers():
    valid, reason = validate_unified_diff("@@ -1 +1 @@\n-old\n+new\n")
    assert valid is False
    assert "file headers" in reason.lower()


def test_validate_unified_diff_rejects_missing_hunk():
    valid, reason = validate_unified_diff("--- a/file.txt\n+++ b/file.txt\n")
    assert valid is False
    assert "missing hunk" in reason.lower()


def test_apply_unified_diff_runs_check_then_apply(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(cmd, input=None, text=None, capture_output=None):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("parallel_agents.patch_tools.subprocess.run", fake_run)
    repo_path = str(tmp_path)

    applied, message = apply_unified_diff(repo_path, VALID_PATCH)
    assert applied is True
    assert "Patch applied" in message
    assert calls[0][-3:] == ["apply", "--check", "-"]
    assert calls[1][-2:] == ["apply", "-"]


def test_apply_unified_diff_returns_check_error(monkeypatch, tmp_path):
    def fake_run(cmd, input=None, text=None, capture_output=None):
        return SimpleNamespace(returncode=1, stdout="", stderr="check failed")

    monkeypatch.setattr("parallel_agents.patch_tools.subprocess.run", fake_run)
    applied, message = apply_unified_diff(str(tmp_path), VALID_PATCH)
    assert applied is False
    assert message == "check failed"
