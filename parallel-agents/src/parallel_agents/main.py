from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from parallel_agents.config import PipelineConfig
from parallel_agents.evidence_store import create_evidence_store
from parallel_agents.models import FinalOutput
from parallel_agents.patch_tools import apply_unified_diff
from parallel_agents.pipeline import Pipeline

console = Console()

EXIT_SUCCESS = 0
EXIT_RUNTIME_FAILURE = 1
EXIT_AUTH_FAILURE = 2
EXIT_PARSE_FAILURE = 3
EXIT_WORKER_FAILURE = 4
EXIT_NO_PATCH = 5
EXIT_PATCH_APPLY_FAILURE = 6


class StreamingProgress:
    """Rich-based streaming progress display for pipeline execution."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []  # (timestamp, message)
        self._live: Live | None = None

    def _render(self) -> Table:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Time", style="dim", width=10)
        table.add_column("Status")

        for ts, msg in self.messages[-20:]:  # show last 20 lines
            if "Done." in msg:
                style = "bold green"
            elif "error" in msg.lower() or "failed" in msg.lower():
                style = "bold red"
            elif "Batch" in msg:
                style = "cyan"
            else:
                style = "white"
            table.add_row(ts, Text(msg, style=style))

        return table

    def update(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.messages.append((ts, msg))
        if self._live:
            self._live.update(self._render())

    def start(self) -> Live:
        self._live = Live(self._render(), console=console, refresh_per_second=4)
        return self._live


def _display_results(output: FinalOutput) -> None:
    console.print()
    console.print(Panel(output.summary, title="Summary", border_style="green"))

    if output.risk_report:
        table = Table(title="Risk Report")
        table.add_column("Severity", style="bold")
        table.add_column("Category")
        table.add_column("Title")
        table.add_column("File")

        for finding in output.risk_report:
            severity_style = {
                "critical": "bold red",
                "high": "red",
                "medium": "yellow",
                "low": "cyan",
                "info": "dim",
            }.get(finding.severity.value, "")
            table.add_row(
                f"[{severity_style}]{finding.severity.value}[/{severity_style}]",
                finding.category,
                finding.title,
                finding.file_path or "-",
            )
        console.print(table)

    if output.pr_summary:
        console.print(Panel(output.pr_summary, title="PR Summary", border_style="blue"))

    if output.patch:
        console.print(Panel(output.patch, title="Patch", border_style="yellow"))

    if output.conflicts_resolved:
        console.print()
        console.print("[bold]Conflicts Resolved:[/bold]")
        for conflict in output.conflicts_resolved:
            console.print(f"  - {conflict.get('issue', 'unknown')}: {conflict.get('resolution', '')}")

    # Worker results table
    worker_table = Table(title="Worker Results")
    worker_table.add_column("Worker")
    worker_table.add_column("Status")
    worker_table.add_column("Findings")
    worker_table.add_column("Recommendations")

    for name, result in output.worker_results.items():
        status_style = "green" if result.status == "success" else ("yellow" if result.status == "partial" else "red")
        worker_table.add_row(
            name,
            f"[{status_style}]{result.status}[/{status_style}]",
            str(len(result.findings)),
            str(len(result.recommendations)),
        )
    console.print(worker_table)

    # Cost summary
    cost = output.metadata.get("cost")
    if cost:
        cost_table = Table(title="Cost Summary")
        cost_table.add_column("Agent")
        cost_table.add_column("Model")
        cost_table.add_column("Input Tokens", justify="right")
        cost_table.add_column("Output Tokens", justify="right")
        cost_table.add_column("Cost (USD)", justify="right")
        cost_table.add_column("Duration", justify="right")

        for agent_name, agent_data in cost.get("agents", {}).items():
            duration_s = agent_data.get("duration_ms", 0) / 1000
            cost_table.add_row(
                agent_name,
                agent_data.get("model", ""),
                f"{agent_data.get('input_tokens', 0):,}",
                f"{agent_data.get('output_tokens', 0):,}",
                f"${agent_data.get('cost_usd', 0):.4f}",
                f"{duration_s:.1f}s",
            )

        cost_table.add_section()
        cost_table.add_row(
            "[bold]Total[/bold]", "",
            f"[bold]{cost.get('total_input_tokens', 0):,}[/bold]",
            f"[bold]{cost.get('total_output_tokens', 0):,}[/bold]",
            f"[bold]${cost.get('total_cost_usd', 0):.4f}[/bold]",
            f"[bold]{cost.get('total_duration_ms', 0) / 1000:.1f}s[/bold]",
        )
        console.print(cost_table)


@click.group()
def cli() -> None:
    """Parallel multi-agent pipeline for code analysis and transformation."""
    pass


@cli.command()
@click.argument("task")
@click.option("--repo", "-r", default=None, help="Path to the repository to analyze")
@click.option("--workers", "-w", default=None, help="Comma-separated list of workers to enable")
@click.option("--disable-workers", "-d", default=None, help="Comma-separated list of workers to disable")
@click.option("--output", "-o", type=click.Choice(["rich", "json", "patch"]), default="rich")
@click.option("--model", "-m", default=None, help="Override model for all agents")
@click.option(
    "--permission-mode",
    type=click.Choice(["default", "acceptEdits", "plan", "bypassPermissions"]),
    default=None,
    help="Override Claude Code permission mode for planner/workers/judge.",
)
@click.option("--store", "-s", type=click.Choice(["file", "sqlite"]), default="file", help="Evidence store backend")
@click.option("--apply-patch/--no-apply-patch", default=False, help="Apply generated patch to repository via git apply.")
@click.option("--streaming/--no-streaming", default=True, help="Enable/disable streaming progress")
def run(
    task: str,
    repo: str | None,
    workers: str | None,
    disable_workers: str | None,
    output: str,
    model: str | None,
    permission_mode: str | None,
    store: str,
    apply_patch: bool,
    streaming: bool,
) -> None:
    """Run the parallel agent pipeline on a task."""
    config = PipelineConfig(store_backend=store)

    if workers:
        enabled = set(workers.split(","))
        for name in config.workers:
            config.workers[name].enabled = name in enabled

    if disable_workers:
        for name in disable_workers.split(","):
            if name in config.workers:
                config.workers[name].enabled = False

    if model:
        config.planner_model = model
        config.judge_model = model
        for wc in config.workers.values():
            wc.model = model
    if permission_mode:
        config.permission_mode = permission_mode

    pipeline = Pipeline(config)

    try:
        if streaming and output == "rich":
            progress = StreamingProgress()
            live = progress.start()
            with live:
                result = asyncio.run(
                    pipeline.run(task, repo_path=repo, on_status=progress.update)
                )
        else:
            def _print_status(msg: str) -> None:
                console.print(f"[bold blue]>[/bold blue] {msg}")

            result = asyncio.run(
                pipeline.run(task, repo_path=repo, on_status=_print_status)
            )
    except Exception as exc:
        exit_code = _classify_exception_exit_code(exc)
        click.echo(f"Run failed: {exc}", err=True)
        sys.exit(exit_code)

    if apply_patch:
        repo_path_for_apply = _resolve_repo_path(repo, task)
        if not repo_path_for_apply:
            click.echo(
                "Cannot apply patch without repository path. "
                "Pass --repo or use a directory as task input.",
                err=True,
            )
            sys.exit(1)
        if not result.patch:
            click.echo("No patch available to apply.", err=True)
            sys.exit(EXIT_NO_PATCH)

        applied, message = apply_unified_diff(repo_path_for_apply, result.patch)
        result.metadata["patch_apply"] = {
            "requested": True,
            "repo_path": repo_path_for_apply,
            "applied": applied,
            "message": message,
        }
        if not applied:
            click.echo(f"Patch apply failed: {message}", err=True)
            sys.exit(EXIT_PATCH_APPLY_FAILURE)
        if output == "rich":
            console.print(f"[bold green]{message}[/bold green]")
    else:
        result.metadata["patch_apply"] = {"requested": False}

    if output == "json":
        click.echo(json.dumps(result.model_dump(), indent=2, default=str))
    elif output == "patch":
        if result.patch:
            click.echo(result.patch)
        else:
            click.echo("No patch generated.", err=True)
            sys.exit(EXIT_NO_PATCH)
    else:
        _display_results(result)

    exit_code = _classify_result_exit_code(result)
    if exit_code != EXIT_SUCCESS:
        sys.exit(exit_code)


@cli.command(name="workers")
def list_workers() -> None:
    """List available workers and their status."""
    config = PipelineConfig()

    table = Table(title="Available Workers")
    table.add_column("Worker")
    table.add_column("Enabled")
    table.add_column("Model")
    table.add_column("Max Turns")
    table.add_column("Timeout (s)")

    for name, wc in config.workers.items():
        enabled_style = "green" if wc.enabled else "dim"
        table.add_row(
            name,
            f"[{enabled_style}]{wc.enabled}[/{enabled_style}]",
            wc.model,
            str(wc.max_turns),
            str(wc.timeout_seconds),
        )
    console.print(table)


@cli.command()
@click.argument("run_id")
@click.option("--store", "-s", type=click.Choice(["file", "sqlite"]), default="file")
@click.option("--output-dir", default=".parallel-agents-output")
def show(run_id: str, store: str, output_dir: str) -> None:
    """View results of a previous run."""
    evidence_store = create_evidence_store(output_dir, run_id, store)

    manifest = evidence_store.load_manifest()
    if not manifest:
        console.print(f"[red]No run found with ID: {run_id}[/red]")
        sys.exit(1)

    console.print(Panel(
        f"Run ID: {manifest.run_id}\n"
        f"Status: {manifest.status.value}\n"
        f"Created: {manifest.created_at}\n"
        f"Input: {manifest.input.raw_input[:100]}\n"
        f"Workers: {', '.join(manifest.workers_invoked)}\n"
        f"Tokens: {manifest.total_tokens:,}\n"
        f"Cost: ${manifest.total_cost_usd:.4f}",
        title="Run Manifest",
        border_style="blue",
    ))

    final = evidence_store.load_final_output()
    if final:
        _display_results(final)
    else:
        console.print("[yellow]No final output found (run may be incomplete)[/yellow]")

        # Show any worker results available
        results = evidence_store.load_all_worker_results()
        if results:
            for name, result in results.items():
                console.print(f"\n[bold]{name}[/bold]: {result.status} - "
                              f"{len(result.findings)} findings, {len(result.recommendations)} recs")


@cli.command()
@click.option("--store", "-s", type=click.Choice(["file", "sqlite"]), default="file")
@click.option("--output-dir", default=".parallel-agents-output")
def history(store: str, output_dir: str) -> None:
    """List previous runs."""
    if store == "sqlite":
        from parallel_agents.evidence_store import SQLiteEvidenceStore
        sqlite_store = SQLiteEvidenceStore(output_dir, "")
        runs = sqlite_store.list_runs()
        if not runs:
            console.print("[dim]No runs found.[/dim]")
            return

        table = Table(title="Run History")
        table.add_column("Run ID")
        table.add_column("Status")
        table.add_column("Created")
        table.add_column("Workers")
        table.add_column("Tokens", justify="right")

        for run in runs:
            table.add_row(
                run.get("run_id", ""),
                run.get("status", ""),
                run.get("created_at", ""),
                ", ".join(run.get("workers_invoked", [])),
                f"{run.get('total_tokens', 0):,}",
            )
        console.print(table)
    else:
        # File-based: list directories
        from pathlib import Path
        output_path = Path(output_dir)
        if not output_path.exists():
            console.print("[dim]No runs found.[/dim]")
            return

        table = Table(title="Run History")
        table.add_column("Run ID")
        table.add_column("Has Manifest")
        table.add_column("Has Output")

        for d in sorted(output_path.iterdir(), reverse=True):
            if d.is_dir():
                table.add_row(
                    d.name,
                    "yes" if (d / "manifest.json").exists() else "no",
                    "yes" if (d / "final_output.json").exists() else "no",
                )
        console.print(table)


@cli.command()
def init() -> None:
    """Create a default configuration file."""
    config = PipelineConfig()
    click.echo(json.dumps(config.model_dump(), indent=2, default=str))
    click.echo("\nCopy the above into .parallel-agents.toml (as TOML) or set PA_ env vars.")


@cli.command(name="mcp")
def mcp_serve() -> None:
    """Start the MCP server (stdio transport).

    Used by AI coding tools (Claude Code, Cursor, Windsurf, Codex CLI,
    Cline, Continue, Amazon Q, Zed) to access parallel-agents as a tool.

    Setup: parallel-agents mcp-install <tool-name>
    """
    try:
        from parallel_agents.mcp_server import run_server
    except ImportError:
        console.print(
            "[red]MCP support requires the 'mcp' package.[/red]\n"
            "Install with: [bold]pip install parallel-agents\\[mcp][/bold]"
        )
        sys.exit(1)
    run_server()


@cli.command(name="mcp-install")
@click.argument(
    "target",
    type=click.Choice([
        "claude-code", "cursor", "windsurf", "cline", "continue",
        "codex", "amazon-q", "zed", "all",
    ]),
)
@click.option(
    "--scope",
    type=click.Choice(["project", "user"]),
    default="project",
    help="Config scope (applies to claude-code only).",
)
def mcp_install(target: str, scope: str) -> None:
    """Install parallel-agents as an MCP server for an AI coding tool.

    Generates the correct config file for the specified tool so it can
    discover and use parallel-agents' analysis tools.

    \b
    Examples:
        parallel-agents mcp-install claude-code
        parallel-agents mcp-install cursor
        parallel-agents mcp-install all --scope user
    """
    from parallel_agents.mcp_installer import install_for_target

    result = install_for_target(target, scope=scope)
    console.print(result)


def _resolve_repo_path(repo: str | None, task: str) -> str | None:
    if repo:
        return repo
    if Path(task).is_dir():
        return task
    return None


def _classify_exception_exit_code(exc: Exception) -> int:
    message = str(exc).lower()
    auth_markers = [
        "unauthorized",
        "authentication",
        "anthropic_api_key",
        "api_key",
        "api key",
        "invalid api key",
    ]
    if any(marker in message for marker in auth_markers):
        return EXIT_AUTH_FAILURE
    return EXIT_RUNTIME_FAILURE


def _classify_result_exit_code(result: FinalOutput) -> int:
    if _has_parse_failure(result):
        return EXIT_PARSE_FAILURE
    if any(worker_result.status == "error" for worker_result in result.worker_results.values()):
        return EXIT_WORKER_FAILURE
    return EXIT_SUCCESS


def _has_parse_failure(result: FinalOutput) -> bool:
    summary = result.summary.lower()
    if "failed to parse" in summary or "parse error" in summary:
        return True

    for worker_result in result.worker_results.values():
        if worker_result.status != "partial" or not worker_result.token_usage:
            continue
        if worker_result.token_usage.get("parsed_structured_output") == 0:
            return True
    return False


if __name__ == "__main__":
    cli()
