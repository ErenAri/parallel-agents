"""Auto-config generator for installing parallel-agents as an MCP server.

Supports: Claude Code, Cursor, Windsurf, Cline, Continue, Codex CLI,
Amazon Q, Zed. Each tool has a different config path, format, and key name.

Usage:
    parallel-agents mcp-install claude-code
    parallel-agents mcp-install cursor
    parallel-agents mcp-install all
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Any


def _detect_server_command() -> list[str]:
    """Detect the best command to start the MCP server.

    Prefers the installed `parallel-agents` binary on PATH.
    Falls back to `python -m parallel_agents.main`.
    """
    if shutil.which("parallel-agents"):
        return ["parallel-agents", "mcp"]
    if shutil.which("parallel-agents-mcp"):
        return ["parallel-agents-mcp"]
    # Fallback: use current Python interpreter
    return [sys.executable, "-m", "parallel_agents.main", "mcp"]


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file, returning empty dict if missing or invalid."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON with proper formatting, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _server_entry(cmd: list[str]) -> dict[str, Any]:
    """Build a standard MCP server entry (command + args format)."""
    return {
        "command": cmd[0],
        "args": cmd[1:] if len(cmd) > 1 else [],
    }


def _home() -> Path:
    """Get the user's home directory."""
    return Path.home()


# ---------------------------------------------------------------------------
# Per-tool installers
# ---------------------------------------------------------------------------


def install_claude_code(scope: str = "project") -> str:
    """Configure parallel-agents for Claude Code CLI.

    Scope:
        project — writes .mcp.json in current directory (version-controllable)
        user    — writes to ~/.claude.json (global, all projects)
    """
    cmd = _detect_server_command()
    entry = _server_entry(cmd)

    if scope == "user":
        config_path = _home() / ".claude.json"
        config = _read_json(config_path)
        config.setdefault("mcpServers", {})
        config["mcpServers"]["parallel-agents"] = entry
        _write_json(config_path, config)
        return f"[green]✓[/green] Claude Code (user): wrote {config_path}"
    else:
        config_path = Path.cwd() / ".mcp.json"
        config = _read_json(config_path)
        config.setdefault("mcpServers", {})
        config["mcpServers"]["parallel-agents"] = entry
        _write_json(config_path, config)
        return f"[green]✓[/green] Claude Code (project): wrote {config_path}"


def install_cursor() -> str:
    """Configure parallel-agents for Cursor IDE."""
    cmd = _detect_server_command()
    config_path = _home() / ".cursor" / "mcp.json"
    config = _read_json(config_path)
    config.setdefault("mcpServers", {})
    config["mcpServers"]["parallel-agents"] = _server_entry(cmd)
    _write_json(config_path, config)
    return f"[green]✓[/green] Cursor: wrote {config_path}"


def install_windsurf() -> str:
    """Configure parallel-agents for Windsurf IDE (Cascade)."""
    cmd = _detect_server_command()
    config_path = _home() / ".codeium" / "windsurf" / "mcp_config.json"
    config = _read_json(config_path)
    config.setdefault("mcpServers", {})
    config["mcpServers"]["parallel-agents"] = _server_entry(cmd)
    _write_json(config_path, config)
    return f"[green]✓[/green] Windsurf: wrote {config_path}"


def install_cline() -> str:
    """Configure parallel-agents for Cline (VS Code extension)."""
    cmd = _detect_server_command()
    config_path = _home() / ".cline" / "mcp.json"
    config = _read_json(config_path)
    config.setdefault("mcpServers", {})
    config["mcpServers"]["parallel-agents"] = _server_entry(cmd)
    _write_json(config_path, config)
    return f"[green]✓[/green] Cline: wrote {config_path}"


def install_continue() -> str:
    """Configure parallel-agents for Continue.dev.

    Note: Continue uses an *array* format for mcpServers, not an object.
    """
    cmd = _detect_server_command()
    config_path = Path.cwd() / ".continue" / "config.json"
    config = _read_json(config_path)

    # Continue uses array format
    servers = config.get("mcpServers", [])
    if not isinstance(servers, list):
        servers = []

    # Remove existing parallel-agents entry if present
    servers = [s for s in servers if s.get("name") != "parallel-agents"]

    servers.append({
        "name": "parallel-agents",
        "command": cmd[0],
        "args": cmd[1:] if len(cmd) > 1 else [],
    })

    config["mcpServers"] = servers
    _write_json(config_path, config)
    return f"[green]✓[/green] Continue: wrote {config_path}"


def install_codex() -> str:
    """Configure parallel-agents for OpenAI Codex CLI.

    Codex uses TOML format and ONLY supports stdio transport.
    """
    cmd = _detect_server_command()
    config_path = _home() / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing TOML content
    existing = ""
    if config_path.exists():
        existing = config_path.read_text(encoding="utf-8")

    # Check if our section already exists
    section_header = "[mcp_servers.parallel-agents]"
    if section_header in existing:
        # Remove existing section (up to next section or end of file)
        lines = existing.split("\n")
        new_lines = []
        skip = False
        for line in lines:
            if line.strip() == section_header:
                skip = True
                continue
            if skip and line.strip().startswith("["):
                skip = False
            if not skip:
                new_lines.append(line)
        existing = "\n".join(new_lines).rstrip() + "\n"

    # Build args TOML array
    args_toml = json.dumps(cmd[1:]) if len(cmd) > 1 else "[]"

    new_section = f"""
{section_header}
command = {json.dumps(cmd[0])}
args = {args_toml}
"""

    config_path.write_text(existing + new_section, encoding="utf-8")
    return f"[green]✓[/green] Codex CLI: wrote {config_path}"


def install_amazon_q() -> str:
    """Configure parallel-agents for Amazon Q Developer CLI."""
    cmd = _detect_server_command()
    config_path = _home() / ".aws" / "amazonq" / "agents" / "default.json"
    config = _read_json(config_path)
    config.setdefault("mcpServers", {})
    config["mcpServers"]["parallel-agents"] = _server_entry(cmd)
    _write_json(config_path, config)
    return f"[green]✓[/green] Amazon Q: wrote {config_path}"


def install_zed() -> str:
    """Configure parallel-agents for Zed editor.

    Note: Zed uses 'context_servers' key, NOT 'mcpServers'.
    """
    cmd = _detect_server_command()

    # Zed config path varies by OS
    system = platform.system()
    if system == "Darwin":
        config_path = _home() / "Library" / "Application Support" / "Zed" / "settings.json"
    elif system == "Windows":
        config_path = Path(os.environ.get("APPDATA", "")) / "Zed" / "settings.json"
    else:
        config_path = _home() / ".config" / "zed" / "settings.json"

    config = _read_json(config_path)
    config.setdefault("context_servers", {})
    config["context_servers"]["parallel-agents"] = _server_entry(cmd)
    _write_json(config_path, config)
    return f"[green]✓[/green] Zed: wrote {config_path}"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

INSTALLER_MAP = {
    "claude-code": install_claude_code,
    "cursor": install_cursor,
    "windsurf": install_windsurf,
    "cline": install_cline,
    "continue": install_continue,
    "codex": install_codex,
    "amazon-q": install_amazon_q,
    "zed": install_zed,
}


def install_for_target(target: str, scope: str = "project") -> str:
    """Install MCP config for a specific tool or all tools.

    Args:
        target: Tool name (e.g., "claude-code", "cursor") or "all".
        scope: Config scope for tools that support it (e.g., "project" or "user").

    Returns:
        Rich-formatted status message.
    """
    if target == "all":
        results = []
        for name, installer in INSTALLER_MAP.items():
            try:
                if name == "claude-code":
                    msg = installer(scope=scope)
                else:
                    msg = installer()
                results.append(msg)
            except Exception as e:
                results.append(f"[red]✗[/red] {name}: {e}")
        return "\n".join(results)

    installer = INSTALLER_MAP.get(target)
    if not installer:
        available = ", ".join(sorted(INSTALLER_MAP.keys()))
        return f"[red]Unknown target '{target}'. Available: {available}, all[/red]"

    try:
        if target == "claude-code":
            return installer(scope=scope)
        return installer()
    except Exception as e:
        return f"[red]✗[/red] {target}: {e}"
