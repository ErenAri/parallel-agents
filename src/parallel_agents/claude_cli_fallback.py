from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from claude_code_sdk import ClaudeCodeOptions

logger = logging.getLogger("parallel_agents.claude_cli_fallback")


async def run_query_via_cli(
    prompt: str,
    options: ClaudeCodeOptions,
) -> tuple[str, float, dict[str, int]]:
    """Run query through Claude CLI stream-json output.

    This path is intentionally tolerant of unknown event types so it remains
    functional even when the SDK parser lags behind new CLI message types.
    """
    cli_path = _find_claude_cli()
    effective_prompt = _with_inlined_system_prompt(prompt, options)
    cmd = _build_cli_command(cli_path, options)
    cwd = str(options.cwd) if options.cwd else None
    stdout, stderr, returncode = await _run_cli_process(
        cmd,
        cwd=cwd,
        stdin_text=effective_prompt,
    )

    if returncode != 0 and _is_missing_print_input_error(stderr):
        logger.warning(
            "Claude CLI rejected stdin prompt; retrying with positional prompt."
        )
        positional_cmd = _build_cli_command(
            cli_path,
            options,
            positional_prompt=effective_prompt,
        )
        stdout, stderr, returncode = await _run_cli_process(
            positional_cmd,
            cwd=cwd,
            stdin_text=None,
        )

    if returncode != 0:
        stderr_excerpt = stderr.strip()[:2000] if stderr else "no stderr"
        raise RuntimeError(
            f"Claude CLI fallback failed with exit code {returncode}: {stderr_excerpt}"
        )

    return _parse_stream_json_output(stdout)


async def _run_cli_process(
    cmd: list[str],
    *,
    cwd: str | None,
    stdin_text: str | None,
) -> tuple[str, str, int]:
    stdin = asyncio.subprocess.PIPE if stdin_text is not None else asyncio.subprocess.DEVNULL

    # Deliver the prompt over stdin rather than as a positional argument.
    # With --print, Claude CLI 2.1.x reads the prompt from stdin whenever stdin
    # is not a TTY (which is always the case under create_subprocess_exec). If
    # stdin is left unset it is empty/closed, and the CLI then rejects the run
    # ("Input must be provided either through stdin or as a prompt argument
    # when using --print") even when a positional prompt follows "--". Piping
    # stdin is the canonical non-interactive form and also avoids mis-parsing
    # prompts that start with "-".
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdin=stdin,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    input_bytes = stdin_text.encode("utf-8") if stdin_text is not None else None
    stdout_bytes, stderr_bytes = await process.communicate(input=input_bytes)
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return stdout, stderr, process.returncode or 0


def _build_cli_command(
    cli_path: str,
    options: ClaudeCodeOptions,
    *,
    positional_prompt: str | None = None,
) -> list[str]:
    cmd = [cli_path, "--output-format", "stream-json", "--verbose"]

    # NOTE:
    # System prompts are inlined into the stdin prompt (see
    # _with_inlined_system_prompt) rather than passed via
    # --system-prompt/--append-system-prompt, which can break --print prompt
    # parsing on Windows with multi-line values.

    if options.allowed_tools:
        cmd.extend(["--allowedTools", ",".join(options.allowed_tools)])

    if options.disallowed_tools:
        cmd.extend(["--disallowedTools", ",".join(options.disallowed_tools)])

    if options.max_turns:
        cmd.extend(["--max-turns", str(options.max_turns)])

    if options.model:
        cmd.extend(["--model", options.model])

    if options.permission_mode:
        cmd.extend(["--permission-mode", options.permission_mode])

    if options.continue_conversation:
        cmd.append("--continue")

    if options.resume:
        cmd.extend(["--resume", options.resume])

    if options.settings:
        cmd.extend(["--settings", options.settings])

    if options.add_dirs:
        for directory in options.add_dirs:
            cmd.extend(["--add-dir", str(directory)])

    if options.mcp_servers:
        cmd.extend(["--mcp-config", _serialize_mcp_servers(options.mcp_servers)])

    if options.include_partial_messages:
        cmd.append("--include-partial-messages")

    for flag, value in options.extra_args.items():
        if value is None:
            cmd.append(f"--{flag}")
        else:
            cmd.extend([f"--{flag}", str(value)])

    cmd.append("--print")
    if positional_prompt is not None:
        cmd.append(positional_prompt)
    return cmd


def _serialize_mcp_servers(mcp_servers: Any) -> str:
    if isinstance(mcp_servers, dict):
        servers_for_cli: dict[str, Any] = {}
        for name, config in mcp_servers.items():
            if isinstance(config, dict) and config.get("type") == "sdk":
                servers_for_cli[name] = {k: v for k, v in config.items() if k != "instance"}
            else:
                servers_for_cli[name] = config
        return json.dumps({"mcpServers": servers_for_cli})
    return str(mcp_servers)


def _parse_stream_json_output(stdout: str) -> tuple[str, float, dict[str, int]]:
    raw_parts: list[str] = []
    result_text = ""
    total_cost = 0.0
    token_usage: dict[str, int] = {}

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue

        message_type = payload.get("type")
        if message_type == "assistant":
            message = payload.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            raw_parts.append(text)
        elif message_type == "result":
            total_cost = float(payload.get("total_cost_usd", 0.0) or 0.0)
            result_text = str(payload.get("result", "") or result_text)
            usage = payload.get("usage")
            if isinstance(usage, dict):
                token_usage = _normalize_usage(usage)
        else:
            # Ignore unknown event types, e.g. rate_limit_event.
            continue

    raw_text = "".join(raw_parts).strip()
    if not raw_text:
        raw_text = result_text
    return raw_text, total_cost, token_usage


def _normalize_usage(usage: dict[str, Any]) -> dict[str, int]:
    def _to_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    return {
        "input_tokens": _to_int(usage.get("input_tokens", usage.get("inputTokens"))),
        "output_tokens": _to_int(usage.get("output_tokens", usage.get("outputTokens"))),
        "cache_read_input_tokens": _to_int(
            usage.get("cache_read_input_tokens", usage.get("cacheReadInputTokens"))
        ),
        "cache_creation_input_tokens": _to_int(
            usage.get(
                "cache_creation_input_tokens",
                usage.get("cacheCreationInputTokens"),
            )
        ),
    }


def _find_claude_cli() -> str:
    found = shutil.which("claude")
    if found:
        executable = _resolve_windows_claude_executable(Path(found))
        if executable:
            return str(executable)
        return found

    fallback_paths = [
        Path.home() / ".local/bin/claude.exe",
        Path.home() / ".npm-global/bin/claude",
        Path.home() / ".local/bin/claude",
        Path("/usr/local/bin/claude"),
    ]
    for path in fallback_paths:
        if path.exists() and path.is_file():
            return str(path)
    raise RuntimeError("Claude CLI binary not found for fallback path.")


def _resolve_windows_claude_executable(found: Path) -> Path | None:
    if os.name != "nt":
        return None
    if found.suffix.lower() not in {".cmd", ".bat", ".ps1"}:
        return found if found.suffix.lower() == ".exe" else None

    candidates = [
        found.with_suffix(".exe"),
        found.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe",
        Path.home() / ".local" / "bin" / "claude.exe",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _is_missing_print_input_error(stderr: str) -> bool:
    return (
        "Input must be provided either through stdin or as a prompt argument"
        in stderr
    )


def _with_inlined_system_prompt(prompt: str, options: ClaudeCodeOptions) -> str:
    system_parts: list[str] = []
    if options.system_prompt:
        system_parts.append(options.system_prompt)
    if options.append_system_prompt:
        system_parts.append(options.append_system_prompt)
    if not system_parts:
        return prompt
    merged_system = "\n\n".join(system_parts)
    return (
        "System instructions:\n"
        f"{merged_system}\n\n"
        "User request:\n"
        f"{prompt}"
    )
