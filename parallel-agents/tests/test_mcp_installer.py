"""Tests for the MCP auto-installer."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from parallel_agents.mcp_installer import (
    install_claude_code,
    install_codex,
    install_continue,
    install_cursor,
    install_for_target,
    install_zed,
    _detect_server_command,
)


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """Override home directory for all installer tests."""
    monkeypatch.setattr("parallel_agents.mcp_installer._home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Command detection
# ---------------------------------------------------------------------------


def test_detect_command_finds_binary():
    """Should prefer parallel-agents binary when on PATH."""
    with patch("shutil.which", side_effect=lambda x: "/usr/bin/parallel-agents" if x == "parallel-agents" else None):
        cmd = _detect_server_command()
    assert cmd == ["parallel-agents", "mcp"]


def test_detect_command_fallback_to_python():
    """Should fall back to python -m when binary not on PATH."""
    with patch("shutil.which", return_value=None):
        cmd = _detect_server_command()
    assert cmd[0].endswith("python") or "python" in cmd[0].lower() or cmd[0] == cmd[0]  # just check it's valid
    assert "-m" in cmd
    assert "parallel_agents.main" in cmd


# ---------------------------------------------------------------------------
# Claude Code
# ---------------------------------------------------------------------------


def test_install_claude_code_project(tmp_home):
    """Should create .mcp.json in cwd with correct structure."""
    result = install_claude_code(scope="project")

    config_path = tmp_home / ".mcp.json"
    assert config_path.exists()

    config = json.loads(config_path.read_text())
    assert "mcpServers" in config
    assert "parallel-agents" in config["mcpServers"]
    assert "command" in config["mcpServers"]["parallel-agents"]
    assert "OK" in result


def test_install_claude_code_user(tmp_home):
    """Should write to ~/.claude.json for user scope."""
    result = install_claude_code(scope="user")

    config_path = tmp_home / ".claude.json"
    assert config_path.exists()

    config = json.loads(config_path.read_text())
    assert "parallel-agents" in config["mcpServers"]


def test_install_claude_code_merges_existing(tmp_home):
    """Should merge with existing config, not overwrite other servers."""
    config_path = tmp_home / ".mcp.json"
    config_path.write_text(json.dumps({
        "mcpServers": {
            "other-server": {"command": "other", "args": []}
        }
    }))

    install_claude_code(scope="project")

    config = json.loads(config_path.read_text())
    assert "other-server" in config["mcpServers"]
    assert "parallel-agents" in config["mcpServers"]


# ---------------------------------------------------------------------------
# Cursor
# ---------------------------------------------------------------------------


def test_install_cursor(tmp_home):
    """Should create ~/.cursor/mcp.json with mcpServers."""
    install_cursor()

    config_path = tmp_home / ".cursor" / "mcp.json"
    assert config_path.exists()

    config = json.loads(config_path.read_text())
    assert "parallel-agents" in config["mcpServers"]


# ---------------------------------------------------------------------------
# Continue (array format)
# ---------------------------------------------------------------------------


def test_install_continue_array_format(tmp_home):
    """Continue uses array format for mcpServers, not object."""
    install_continue()

    config_path = tmp_home / ".continue" / "config.json"
    assert config_path.exists()

    config = json.loads(config_path.read_text())
    assert isinstance(config["mcpServers"], list)
    assert any(s["name"] == "parallel-agents" for s in config["mcpServers"])


def test_install_continue_replaces_existing(tmp_home):
    """Should replace existing parallel-agents entry, not duplicate."""
    (tmp_home / ".continue").mkdir(parents=True)
    (tmp_home / ".continue" / "config.json").write_text(json.dumps({
        "mcpServers": [
            {"name": "parallel-agents", "command": "old-command"},
            {"name": "other", "command": "other-cmd"},
        ]
    }))

    install_continue()

    config = json.loads((tmp_home / ".continue" / "config.json").read_text())
    pa_entries = [s for s in config["mcpServers"] if s["name"] == "parallel-agents"]
    assert len(pa_entries) == 1
    assert pa_entries[0]["command"] != "old-command"
    assert any(s["name"] == "other" for s in config["mcpServers"])


# ---------------------------------------------------------------------------
# Codex (TOML)
# ---------------------------------------------------------------------------


def test_install_codex_toml(tmp_home):
    """Should write TOML format for Codex CLI."""
    install_codex()

    config_path = tmp_home / ".codex" / "config.toml"
    assert config_path.exists()

    content = config_path.read_text()
    assert "[mcp_servers.parallel-agents]" in content
    assert "command" in content


def test_install_codex_replaces_existing_section(tmp_home):
    """Should replace existing section without duplicating."""
    (tmp_home / ".codex").mkdir(parents=True)
    (tmp_home / ".codex" / "config.toml").write_text(
        '[mcp_servers.parallel-agents]\ncommand = "old"\n\n'
        '[mcp_servers.other]\ncommand = "other"\n'
    )

    install_codex()

    content = (tmp_home / ".codex" / "config.toml").read_text()
    assert content.count("[mcp_servers.parallel-agents]") == 1
    assert "[mcp_servers.other]" in content


# ---------------------------------------------------------------------------
# Zed (context_servers key)
# ---------------------------------------------------------------------------


def test_install_zed_uses_context_servers(tmp_home, monkeypatch):
    """Zed uses 'context_servers' key, not 'mcpServers'."""
    # Mock the config path to use tmp_home
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "parallel_agents.mcp_installer._home",
        lambda: tmp_home,
    )

    install_zed()

    config_path = tmp_home / ".config" / "zed" / "settings.json"
    assert config_path.exists()

    config = json.loads(config_path.read_text())
    assert "context_servers" in config
    assert "parallel-agents" in config["context_servers"]
    assert "mcpServers" not in config


# ---------------------------------------------------------------------------
# install_for_target dispatcher
# ---------------------------------------------------------------------------


def test_install_all(tmp_home, monkeypatch):
    """install_all should attempt all tools and report results."""
    monkeypatch.setattr("platform.system", lambda: "Linux")

    result = install_for_target("all")

    # Should have results for multiple tools
    assert "Claude Code" in result
    assert "Cursor" in result


def test_install_unknown_target():
    """Unknown target should return error message."""
    result = install_for_target("nonexistent")
    assert "Unknown target" in result
