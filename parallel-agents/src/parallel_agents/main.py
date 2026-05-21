from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from parallel_agents.config import PipelineConfig
from parallel_agents.eval_harness import (
    compute_evaluation_score,
    load_evaluation_dataset,
    load_evaluation_results,
    render_evaluation_report,
    run_evaluation,
    save_evaluation_results,
    save_evaluation_score,
)
from parallel_agents.company_workflows import (
    RoadmapPlan,
    ProductBrief,
    ReleaseReadinessReport,
    build_architecture_rfc,
    build_branch_name,
    build_github_workflow_templates,
    build_issue_plan_from_roadmap,
    build_post_release_review,
    build_prfaq,
    build_release_readiness_report,
    build_roadmap,
    build_sprint_plan,
    create_product_brief,
    recommend_tech_stack,
    render_pr_summary,
)
from parallel_agents.company_artifacts import (
    append_company_artifact_event,
    list_company_artifact_paths,
    load_company_artifact,
    persist_company_artifact,
)
from parallel_agents.company_policy import (
    CompanyApplyPolicy,
    derive_policy_from_issue_plan,
    validate_issue_plan_against_policy,
)
from parallel_agents.evidence_store import create_evidence_store
from parallel_agents.models import FinalOutput
from parallel_agents.patch_tools import apply_unified_diff
from parallel_agents.pipeline import Pipeline
from parallel_agents.tools.github_tools import (
    create_issue,
    ensure_milestone,
    parse_repo_ref,
)

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


@cli.group(name="eval")
def eval_group() -> None:
    """Evaluation tooling for productivity and effectiveness benchmarking."""
    pass


@eval_group.command(name="run")
@click.option(
    "--dataset",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to evaluation dataset JSON.",
)
@click.option(
    "--output",
    default="eval/results.json",
    type=click.Path(path_type=Path),
    show_default=True,
    help="Output JSON file for run records.",
)
@click.option(
    "--repo-root",
    default=None,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Base directory used to resolve relative repo paths in dataset cases.",
)
@click.option("--workers", "-w", default=None, help="Comma-separated list of workers to enable")
@click.option("--disable-workers", "-d", default=None, help="Comma-separated list of workers to disable")
@click.option("--model", "-m", default=None, help="Override model for all agents")
@click.option(
    "--permission-mode",
    type=click.Choice(["default", "acceptEdits", "plan", "bypassPermissions"]),
    default=None,
    help="Override Claude Code permission mode for planner/workers/judge.",
)
@click.option("--store", "-s", type=click.Choice(["file", "sqlite"]), default="file", help="Evidence store backend")
@click.option("--max-cases", type=int, default=None, help="Limit number of cases from dataset")
def eval_run(
    dataset: Path,
    output: Path,
    repo_root: Path | None,
    workers: str | None,
    disable_workers: str | None,
    model: str | None,
    permission_mode: str | None,
    store: str,
    max_cases: int | None,
) -> None:
    """Run benchmark dataset through the pipeline and persist measurements."""
    if max_cases is not None and max_cases <= 0:
        click.echo("--max-cases must be greater than 0.", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

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

    dataset_obj = load_evaluation_dataset(dataset)
    if max_cases is not None:
        dataset_obj = dataset_obj.model_copy(
            update={"cases": dataset_obj.cases[:max_cases]}
        )

    if not dataset_obj.cases:
        click.echo("Dataset contains no cases to evaluate.", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    def _status(msg: str) -> None:
        console.print(f"[bold blue]>[/bold blue] {msg}")

    try:
        results = asyncio.run(
            run_evaluation(
                dataset_obj,
                dataset_path=dataset,
                config=config,
                repo_root=repo_root,
                on_status=_status,
            )
        )
    except Exception as exc:
        click.echo(f"Evaluation run failed: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    save_evaluation_results(output, results)
    console.print(
        f"[bold green]Evaluation run complete.[/bold green] "
        f"Saved results to: {output}"
    )


@eval_group.command(name="score")
@click.option(
    "--results",
    "results_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to evaluation results JSON.",
)
@click.option(
    "--output-json",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional path to save computed score JSON.",
)
@click.option(
    "--output-report",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional path to save Markdown report.",
)
@click.option("--json-output/--no-json-output", default=False, help="Print score as JSON to stdout.")
def eval_score(
    results_path: Path,
    output_json: Path | None,
    output_report: Path | None,
    json_output: bool,
) -> None:
    """Score evaluation results and compute proof-oriented metrics."""
    results = load_evaluation_results(results_path)
    score = compute_evaluation_score(results)

    if output_json:
        save_evaluation_score(output_json, score)

    report = render_evaluation_report(results, score)
    if output_report:
        output_report.parent.mkdir(parents=True, exist_ok=True)
        output_report.write_text(report, encoding="utf-8")

    if json_output:
        click.echo(json.dumps(score.model_dump(mode="json"), indent=2, default=str))
        return

    table = Table(title="Evaluation Scorecard")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Cases", str(score.case_count))
    table.add_row("Completed", str(score.completed_count))
    table.add_row("Failed", str(score.failed_count))
    table.add_row("Speed Gain (median)", _fmt_percent(score.speed_gain_median))
    table.add_row("Acceptance Rate", _fmt_percent(score.acceptance_rate))
    table.add_row("Regression Rate", _fmt_percent(score.regression_rate))
    table.add_row("Finding Precision", _fmt_percent(score.finding_precision))
    table.add_row(
        "Weighted Delivery Impact",
        _fmt_percent(score.weighted_delivery_impact_score),
    )
    console.print(table)

    if output_report:
        console.print(f"[green]Markdown report written to {output_report}[/green]")
    if output_json:
        console.print(f"[green]Score JSON written to {output_json}[/green]")


@cli.group(name="company")
def company_group() -> None:
    """Company workflow tooling for idea-to-release planning artifacts."""
    pass


@company_group.command(name="idea")
@click.argument("idea")
@click.option("--title", default=None, help="Optional project title override.")
@click.option(
    "--output",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional output path for generated brief JSON.",
)
@click.option("--run-id", default=None, help="Optional run ID for artifact linking.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_idea(
    idea: str,
    title: str | None,
    output: Path | None,
    run_id: str | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Create a ProductBrief artifact from a project idea."""
    try:
        artifact = create_product_brief(idea=idea, title=title)
    except Exception as exc:
        click.echo(f"Failed to create product brief: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    _emit_artifact(
        artifact,
        output=output,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name="brief",
        json_output=json_output,
        panel_title="Product Brief",
        summary_lines=[
            f"ID: {artifact.id}",
            f"Title: {artifact.title}",
            f"Problem: {artifact.problem_statement}",
            f"Goals: {len(artifact.goals)}",
            f"Success metrics: {len(artifact.success_metrics)}",
        ],
    )


@company_group.command(name="prfaq")
@click.option(
    "--brief",
    "brief_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to ProductBrief JSON.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional output path for generated PR/FAQ JSON.",
)
@click.option("--run-id", default=None, help="Optional run ID for artifact linking.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_prfaq(
    brief_path: Path,
    output: Path | None,
    run_id: str | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Generate a PR/FAQ artifact from a ProductBrief."""
    try:
        brief = _load_model_from_json(brief_path, ProductBrief)
        artifact = build_prfaq(brief)
    except Exception as exc:
        click.echo(f"Failed to build PR/FAQ: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    _emit_artifact(
        artifact,
        output=output,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name="prfaq",
        json_output=json_output,
        panel_title="PR/FAQ",
        summary_lines=[
            f"Headline: {artifact.headline}",
            f"Customer FAQ items: {len(artifact.customer_faq)}",
            f"Internal FAQ items: {len(artifact.internal_faq)}",
            f"Launch criteria: {len(artifact.launch_criteria)}",
        ],
    )


@company_group.command(name="stack")
@click.option(
    "--repo",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    show_default=True,
    help="Repository path to analyze.",
)
@click.option(
    "--focus",
    default="AI software delivery workflow",
    help="Product focus context to include in recommendation.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional output path for generated stack decision JSON.",
)
@click.option("--run-id", default=None, help="Optional run ID for artifact linking.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_stack(
    repo: Path,
    focus: str,
    output: Path | None,
    run_id: str | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Recommend an initial technology stack based on repository signals."""
    try:
        artifact = recommend_tech_stack(repo_path=repo, product_focus=focus)
    except Exception as exc:
        click.echo(f"Failed to recommend tech stack: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    _emit_artifact(
        artifact,
        output=output,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name="stack",
        json_output=json_output,
        panel_title="Tech Stack Decision",
        summary_lines=[
            f"Recommended: {artifact.recommended_option}",
            f"Detected signals: {', '.join(artifact.detected_signals) if artifact.detected_signals else 'none'}",
            f"Options scored: {len(artifact.options)}",
            f"Risks: {len(artifact.risks)}",
        ],
    )


@company_group.command(name="rfc")
@click.option(
    "--brief",
    "brief_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to ProductBrief JSON.",
)
@click.option(
    "--repo",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    show_default=True,
    help="Repository path for stack analysis context.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional output path for generated RFC JSON.",
)
@click.option("--run-id", default=None, help="Optional run ID for artifact linking.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_rfc(
    brief_path: Path,
    repo: Path,
    output: Path | None,
    run_id: str | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Generate an Architecture RFC from ProductBrief and stack recommendation."""
    try:
        brief = _load_model_from_json(brief_path, ProductBrief)
        stack = recommend_tech_stack(repo_path=repo)
        artifact = build_architecture_rfc(brief, stack)
    except Exception as exc:
        click.echo(f"Failed to build architecture RFC: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    _emit_artifact(
        artifact,
        output=output,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name="rfc",
        json_output=json_output,
        panel_title="Architecture RFC",
        summary_lines=[
            f"RFC ID: {artifact.id}",
            f"Title: {artifact.title}",
            f"Status: {artifact.status}",
            f"Alternatives: {len(artifact.alternatives)}",
        ],
    )


@company_group.command(name="roadmap")
@click.option(
    "--brief",
    "brief_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to ProductBrief JSON.",
)
@click.option(
    "--horizon-weeks",
    default=12,
    type=int,
    show_default=True,
    help="Planning horizon in weeks.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional output path for generated roadmap JSON.",
)
@click.option("--run-id", default=None, help="Optional run ID for artifact linking.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_roadmap(
    brief_path: Path,
    horizon_weeks: int,
    output: Path | None,
    run_id: str | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Create a roadmap artifact from a ProductBrief."""
    if horizon_weeks <= 0:
        click.echo("--horizon-weeks must be greater than 0.", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    try:
        brief = _load_model_from_json(brief_path, ProductBrief)
        artifact = build_roadmap(brief, horizon_weeks=horizon_weeks)
    except Exception as exc:
        click.echo(f"Failed to build roadmap: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    _emit_artifact(
        artifact,
        output=output,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name="roadmap",
        json_output=json_output,
        panel_title="Roadmap",
        summary_lines=[
            f"Name: {artifact.name}",
            f"Horizon weeks: {artifact.horizon_weeks}",
            f"Outcomes: {len(artifact.outcomes)}",
            f"Items: {len(artifact.items)}",
        ],
    )


@company_group.command(name="release-check")
@click.option(
    "--repo",
    default=".",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    show_default=True,
    help="Repository path to evaluate.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional output path for generated release readiness JSON.",
)
@click.option("--run-id", default=None, help="Optional run ID for artifact linking.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_release_check(
    repo: Path,
    output: Path | None,
    run_id: str | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Evaluate release readiness checks for a repository."""
    try:
        artifact = build_release_readiness_report(repo)
    except Exception as exc:
        click.echo(f"Failed to run release readiness checks: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    _emit_artifact(
        artifact,
        output=output,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name="release-check",
        json_output=json_output,
        panel_title="Release Readiness",
        summary_lines=[
            f"Repository: {artifact.repo_path}",
            f"Status: {artifact.status}",
            f"Checks: {len(artifact.items)}",
            f"Blocking issues: {len(artifact.blocking_issues)}",
        ],
    )


@company_group.command(name="sprint")
@click.option(
    "--roadmap",
    "roadmap_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to RoadmapPlan JSON.",
)
@click.option("--milestone", required=True, help="Roadmap milestone to include in the sprint.")
@click.option("--horizon-days", default=14, type=int, show_default=True, help="Sprint planning horizon in days.")
@click.option(
    "--output",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional output path for generated sprint plan JSON.",
)
@click.option("--run-id", default=None, help="Optional run ID for artifact linking.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_sprint(
    roadmap_path: Path,
    milestone: str,
    horizon_days: int,
    output: Path | None,
    run_id: str | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Create a SprintPlan artifact from a roadmap milestone."""
    try:
        roadmap = _load_model_from_json(roadmap_path, RoadmapPlan)
        artifact = build_sprint_plan(roadmap, milestone=milestone, horizon_days=horizon_days)
    except Exception as exc:
        click.echo(f"Failed to build sprint plan: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    _emit_artifact(
        artifact,
        output=output,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name="sprint",
        json_output=json_output,
        panel_title="Sprint Plan",
        summary_lines=[
            f"Name: {artifact.name}",
            f"Milestone: {artifact.milestone}",
            f"Horizon days: {artifact.horizon_days}",
            f"Items: {len(artifact.items)}",
        ],
    )


@company_group.command(name="post-release")
@click.option("--release-id", required=True, help="Release identifier to review.")
@click.option(
    "--release-check",
    "release_check_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to ReleaseReadinessReport JSON.",
)
@click.option(
    "--metrics",
    "metrics_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional metrics JSON file to include in the review.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional output path for post-release review JSON.",
)
@click.option("--run-id", default=None, help="Optional run ID for artifact linking.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_post_release(
    release_id: str,
    release_check_path: Path,
    metrics_path: Path | None,
    output: Path | None,
    run_id: str | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Create a PostReleaseReview artifact from release readiness output."""
    try:
        release_report = _load_model_from_json(release_check_path, ReleaseReadinessReport)
    except Exception as exc:
        click.echo(f"Failed to load release check: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    try:
        metrics = _load_optional_json(metrics_path)
        artifact = build_post_release_review(
            release_id=release_id,
            release_report=release_report,
            metrics=metrics,
        )
    except Exception as exc:
        click.echo(f"Failed to build post-release review: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    _emit_artifact(
        artifact,
        output=output,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name="post-release",
        json_output=json_output,
        panel_title="Post-Release Review",
        summary_lines=[
            f"Release ID: {artifact.release_id}",
            f"Outcomes: {len(artifact.outcomes)}",
            f"Incidents: {len(artifact.incidents)}",
            f"Follow-ups: {len(artifact.follow_up_items)}",
        ],
    )


@company_group.command(name="templates")
@click.option(
    "--roadmap",
    "roadmap_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional RoadmapPlan JSON used to derive milestone templates.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional output path for GitHub workflow templates JSON.",
)
@click.option("--run-id", default=None, help="Optional run ID for artifact linking.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_templates(
    roadmap_path: Path | None,
    output: Path | None,
    run_id: str | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Generate recommended GitHub labels, milestones, and branch policy."""
    try:
        roadmap = _load_model_from_json(roadmap_path, RoadmapPlan) if roadmap_path else None
        artifact = build_github_workflow_templates(roadmap)
    except Exception as exc:
        click.echo(f"Failed to build templates: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    _emit_artifact(
        artifact,
        output=output,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name="templates",
        json_output=json_output,
        panel_title="GitHub Workflow Templates",
        summary_lines=[
            f"Labels: {len(artifact['labels'])}",
            f"Milestones: {len(artifact['milestones'])}",
            f"Branch format: {artifact['branch_policy']['format']}",
        ],
    )


@company_group.command(name="branch-name")
@click.option("--issue", required=True, help="Issue ID or roadmap source item ID.")
@click.option("--title", required=True, help="Issue or roadmap title.")
@click.option("--prefix", default="pa", show_default=True, help="Branch prefix.")
@click.option("--max-length", default=80, type=int, show_default=True, help="Maximum branch length.")
@click.option("--json-output/--no-json-output", default=False, help="Print payload as JSON.")
def company_branch_name(
    issue: str,
    title: str,
    prefix: str,
    max_length: int,
    json_output: bool,
) -> None:
    """Generate a stable branch name for a planned issue."""
    if max_length < 10:
        click.echo("--max-length must be at least 10.", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)
    branch = build_branch_name(issue, title, prefix=prefix, max_length=max_length)
    payload = {
        "issue": issue,
        "title": title,
        "branch": branch,
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return
    click.echo(branch)


@company_group.command(name="pr-summary")
@click.option("--run-id", required=True, help="Run ID containing final output and artifacts.")
@click.option(
    "--output",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional output path for generated PR summary Markdown.",
)
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print payload as JSON.")
def company_pr_summary(
    run_id: str,
    output: Path | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Generate a PR summary from a stored run final output."""
    try:
        final_output = _load_run_final_output_payload(output_dir, run_id)
        artifacts = list_company_artifact_paths(output_dir, run_id)
        summary = render_pr_summary(final_output, run_id=run_id, artifacts=artifacts)
    except Exception as exc:
        click.echo(f"Failed to build PR summary: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(summary, encoding="utf-8")

    payload = {
        "run_id": run_id,
        "summary": summary,
        "output": str(output.resolve()) if output else None,
        "artifacts": artifacts,
    }
    if json_output:
        click.echo(json.dumps(payload, indent=2, default=str))
        return
    click.echo(summary)
    if output:
        console.print(f"[green]PR summary written to {output}[/green]")


@company_group.command(name="plan")
@click.option(
    "--roadmap",
    "roadmap_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to RoadmapPlan JSON.",
)
@click.option(
    "--repo",
    "repo_ref",
    required=True,
    help="Target GitHub repository (owner/repo or GitHub URL).",
)
@click.option(
    "--labels",
    default="planning,ai-agents",
    show_default=True,
    help="Comma-separated labels to apply to created issues.",
)
@click.option(
    "--create-milestones/--no-create-milestones",
    default=True,
    show_default=True,
    help="Ensure roadmap milestones exist on GitHub before issue creation.",
)
@click.option(
    "--dry-run/--no-dry-run",
    default=True,
    show_default=True,
    help="Preview planned issue creation without writing to GitHub.",
)
@click.option(
    "--permission-profile",
    type=click.Choice(["safe", "team", "owner", "autonomous"]),
    default="team",
    show_default=True,
    help="Write-control profile for plan execution.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(path_type=Path),
    help="Optional output path for issue plan JSON.",
)
@click.option(
    "--policy-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional policy JSON file to constrain apply-time GitHub writes.",
)
@click.option("--run-id", default=None, help="Optional run ID for artifact linking.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_plan(
    roadmap_path: Path,
    repo_ref: str,
    labels: str,
    create_milestones: bool,
    dry_run: bool,
    permission_profile: str,
    output: Path | None,
    policy_file: Path | None,
    run_id: str | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Convert roadmap items into GitHub milestone and issue operations."""
    try:
        roadmap = _load_model_from_json(roadmap_path, RoadmapPlan)
    except Exception as exc:
        click.echo(f"Failed to load roadmap: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    parsed_repo = parse_repo_ref(repo_ref)
    if not parsed_repo:
        click.echo("Failed to parse --repo. Use owner/repo or a GitHub repository URL.", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)
    owner, repo = parsed_repo
    label_list = [label.strip() for label in labels.split(",") if label.strip()]
    issue_plan = build_issue_plan_from_roadmap(roadmap, default_labels=label_list)
    repo_ref = f"{owner}/{repo}"

    try:
        apply_policy = _resolve_company_apply_policy(
            repo_ref=repo_ref,
            issue_plan=issue_plan,
            policy_file=policy_file,
        )
    except Exception as exc:
        click.echo(f"Failed to load apply policy: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    if permission_profile == "safe":
        dry_run = True

    if permission_profile == "team" and not dry_run and not run_id:
        click.echo("Team profile with --no-dry-run requires --run-id for approval workflow.", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    try:
        if permission_profile == "team" and not dry_run:
            result = _build_pending_company_issue_plan(
                owner=owner,
                repo=repo,
                issue_plan=issue_plan,
                create_milestones=create_milestones,
                apply_policy=apply_policy,
            )
        else:
            result = asyncio.run(
                _execute_company_issue_plan(
                    owner=owner,
                    repo=repo,
                    issue_plan=issue_plan,
                    create_milestones=create_milestones,
                    dry_run=dry_run,
                )
            )
            result["requires_approval"] = False
            result["approved"] = permission_profile in {"owner", "autonomous"}
            result["approval_status"] = "not_required"
            result["permission_profile"] = permission_profile
            result["apply_policy"] = apply_policy.model_dump(mode="json")
    except Exception as exc:
        click.echo(f"Failed to execute company plan: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    _attach_run_metadata(result, run_id=run_id, artifact_name="issue-plan")

    _emit_artifact(
        result,
        output=output,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name="issue-plan",
        json_output=json_output,
        panel_title="Company Plan",
        summary_lines=[
            f"Repository: {result['repo']}",
            f"Dry run: {result['dry_run']}",
            f"Permission profile: {result.get('permission_profile', permission_profile)}",
            f"Approval status: {result.get('approval_status', 'n/a')}",
            f"Milestones tracked: {len(result['milestones'])}",
            f"Issues planned: {len(result['issues'])}",
            f"Issues created: {sum(1 for issue in result['issues'] if issue.get('created'))}",
        ],
    )


@company_group.command(name="approve")
@click.option("--run-id", required=True, help="Run ID containing the pending plan artifact.")
@click.option("--artifact", "artifact_name", default="issue-plan", show_default=True, help="Artifact name to approve.")
@click.option("--approver", default=None, help="Optional approver identity.")
@click.option("--approval-note", default=None, help="Optional note captured in immutable approval audit log.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_approve(
    run_id: str,
    artifact_name: str,
    approver: str | None,
    approval_note: str | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Approve a pending company issue plan."""
    artifact = load_company_artifact(output_dir, run_id, artifact_name)
    if not artifact:
        click.echo(f"No artifact named '{artifact_name}' found for run {run_id}.", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    approved_by = (
        approver
        or os.environ.get("USERNAME")
        or os.environ.get("USER")
        or "manual-approval"
    )
    approved_at = datetime.now(timezone.utc).isoformat()
    prior_status = str(artifact.get("approval_status", "unknown"))
    approval_note_value = approval_note.strip() if approval_note else None

    artifact["approved"] = True
    artifact["approval_status"] = "approved"
    artifact["approved_at"] = approved_at
    artifact["approved_by"] = approved_by
    if approval_note_value:
        artifact["approval_note"] = approval_note_value
    artifact.setdefault("requires_approval", True)

    try:
        audit_path = append_company_artifact_event(
            output_dir=output_dir,
            run_id=run_id,
            artifact_name=artifact_name,
            event_payload={
                "event": "approval_granted",
                "artifact": artifact_name,
                "run_id": run_id,
                "previous_status": prior_status,
                "approval_status": artifact["approval_status"],
                "approved_by": approved_by,
                "approved_at": approved_at,
                "approval_note": approval_note_value,
            },
        )
    except Exception as exc:
        click.echo(f"Failed to append approval audit log: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    artifact["approval_log_path"] = str(audit_path.resolve())

    _emit_artifact(
        artifact,
        output=None,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name=artifact_name,
        json_output=json_output,
        panel_title="Plan Approval",
        summary_lines=[
            f"Run ID: {run_id}",
            f"Artifact: {artifact_name}",
            f"Approved by: {artifact['approved_by']}",
            f"Approval status: {artifact['approval_status']}",
            f"Audit log: {artifact['approval_log_path']}",
        ],
    )


@company_group.command(name="apply")
@click.option("--run-id", required=True, help="Run ID containing approved plan artifact.")
@click.option("--artifact", "artifact_name", default="issue-plan", show_default=True, help="Artifact name to apply.")
@click.option(
    "--policy-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Optional policy JSON file. Overrides policy embedded in the artifact.",
)
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact as JSON.")
def company_apply(
    run_id: str,
    artifact_name: str,
    policy_file: Path | None,
    output_dir: str,
    json_output: bool,
) -> None:
    """Apply an approved company issue plan to GitHub."""
    artifact = load_company_artifact(output_dir, run_id, artifact_name)
    if not artifact:
        click.echo(f"No artifact named '{artifact_name}' found for run {run_id}.", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    if artifact.get("requires_approval") and not artifact.get("approved"):
        click.echo(
            "Plan is not approved yet. Run `parallel-agents company approve --run-id <id>` first.",
            err=True,
        )
        sys.exit(EXIT_RUNTIME_FAILURE)

    parsed_repo = parse_repo_ref(str(artifact.get("repo", "")))
    if not parsed_repo:
        click.echo("Artifact repo is invalid or missing.", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)
    owner, repo = parsed_repo

    issue_plan_payload = artifact.get("issue_plan", [])
    if not issue_plan_payload:
        click.echo("Artifact has no issue_plan payload to apply.", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    try:
        policy, policy_source = _resolve_apply_policy_for_artifact(
            artifact=artifact,
            repo_ref=f"{owner}/{repo}",
            issue_plan=issue_plan_payload,
            policy_file=policy_file,
        )
    except Exception as exc:
        click.echo(f"Failed to load apply policy: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)
    violations = validate_issue_plan_against_policy(
        repo_ref=f"{owner}/{repo}",
        issue_plan=issue_plan_payload,
        policy=policy,
    )
    if violations:
        click.echo("Apply policy check failed; no GitHub writes were attempted.", err=True)
        for violation in violations:
            click.echo(f"- {violation}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    try:
        result = asyncio.run(
            _execute_company_issue_plan(
                owner=owner,
                repo=repo,
                issue_plan=issue_plan_payload,
                create_milestones=bool(artifact.get("create_milestones", True)),
                dry_run=False,
            )
        )
    except Exception as exc:
        click.echo(f"Failed to apply approved plan: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    result["requires_approval"] = bool(artifact.get("requires_approval", False))
    result["approved"] = bool(artifact.get("approved", False))
    result["approved_by"] = artifact.get("approved_by")
    result["approved_at"] = artifact.get("approved_at")
    result["approval_status"] = "applied"
    result["permission_profile"] = artifact.get("permission_profile", "team")
    result["applied_at"] = datetime.now(timezone.utc).isoformat()
    result["create_milestones"] = bool(artifact.get("create_milestones", True))
    result["apply_policy"] = policy.model_dump(mode="json")
    result["apply_policy_source"] = policy_source
    _attach_run_metadata(result, run_id=run_id, artifact_name=artifact_name)

    _emit_artifact(
        result,
        output=None,
        run_id=run_id,
        output_dir=output_dir,
        artifact_name=artifact_name,
        json_output=json_output,
        panel_title="Plan Applied",
        summary_lines=[
            f"Repository: {result['repo']}",
            f"Issues planned: {len(result['issues'])}",
            f"Issues created: {sum(1 for issue in result['issues'] if issue.get('created'))}",
            f"Policy source: {policy_source}",
            f"Applied at: {result['applied_at']}",
        ],
    )


@company_group.command(name="artifacts")
@click.option("--run-id", required=True, help="Run ID to inspect.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Artifact output directory for run-linked data.")
@click.option("--json-output/--no-json-output", default=False, help="Print artifact map as JSON.")
def company_artifacts(run_id: str, output_dir: str, json_output: bool) -> None:
    """List run-linked company artifacts."""
    artifacts = list_company_artifact_paths(output_dir, run_id)
    payload = {
        "run_id": run_id,
        "output_dir": str(Path(output_dir).resolve()),
        "count": len(artifacts),
        "artifacts": artifacts,
    }

    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    table = Table(title=f"Company Artifacts ({run_id})")
    table.add_column("Artifact")
    table.add_column("Path")
    for name, path in sorted(artifacts.items()):
        table.add_row(name, path)
    if not artifacts:
        table.add_row("-", "No artifacts found")
    console.print(table)


@cli.group(name="gateway")
def gateway_group() -> None:
    """Local gateway and job API for no-code workflows."""
    pass


@gateway_group.command(name="start")
@click.option("--host", default="127.0.0.1", show_default=True, help="Host address to bind.")
@click.option("--port", default=8733, type=int, show_default=True, help="Port to bind.")
@click.option("--output-dir", default=".parallel-agents-output", show_default=True, help="Gateway state and artifact directory.")
@click.option(
    "--api-key",
    default=None,
    help="Optional gateway API key. If omitted, PA_GATEWAY_API_KEY from env is used.",
)
def gateway_start(host: str, port: int, output_dir: str, api_key: str | None) -> None:
    """Start the local gateway HTTP server."""
    try:
        from parallel_agents.gateway import run_gateway_server
    except Exception as exc:
        click.echo(f"Gateway support is unavailable: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)

    try:
        run_gateway_server(host=host, port=port, output_dir=output_dir, api_key=api_key)
    except Exception as exc:
        click.echo(f"Failed to start gateway: {exc}", err=True)
        sys.exit(EXIT_RUNTIME_FAILURE)


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


async def _execute_company_issue_plan(
    *,
    owner: str,
    repo: str,
    issue_plan: list[Any],
    create_milestones: bool,
    dry_run: bool,
) -> dict[str, Any]:
    milestone_results: list[dict[str, Any]] = []
    issue_results: list[dict[str, Any]] = []
    milestone_seen: set[str] = set()
    normalized_plan: list[dict[str, Any]] = []

    for planned_issue in issue_plan:
        source_item_id = str(_issue_field(planned_issue, "source_item_id", ""))
        title = str(_issue_field(planned_issue, "title", ""))
        body = str(_issue_field(planned_issue, "body", ""))
        milestone_name = str(_issue_field(planned_issue, "milestone", ""))
        raw_labels = _issue_field(planned_issue, "labels", [])
        labels = list(raw_labels) if isinstance(raw_labels, list) else []

        normalized_plan.append({
            "source_item_id": source_item_id,
            "title": title,
            "body": body,
            "milestone": milestone_name,
            "labels": labels,
        })

        if milestone_name and milestone_name not in milestone_seen:
            milestone_seen.add(milestone_name)
            milestone_entry = {
                "title": milestone_name,
                "ensured": False,
                "created": False,
                "status": "skipped",
            }
            if create_milestones:
                if dry_run:
                    milestone_entry["status"] = "planned"
                else:
                    ensured = await ensure_milestone(owner, repo, milestone_name)
                    milestone_entry["ensured"] = ensured is not None
                    milestone_entry["created"] = ensured is not None
                    milestone_entry["status"] = "ensured" if ensured else "failed"
            milestone_results.append(milestone_entry)

        issue_entry = {
            "source_item_id": source_item_id,
            "title": title,
            "milestone": milestone_name,
            "labels": labels,
            "created": False,
            "url": None,
            "status": "planned" if dry_run else "pending",
        }
        if not dry_run:
            issue_url = await create_issue(
                owner,
                repo,
                title,
                body,
                milestone=milestone_name or None,
                labels=labels,
            )
            issue_entry["created"] = issue_url is not None
            issue_entry["url"] = issue_url
            issue_entry["status"] = "created" if issue_url else "failed"
        issue_results.append(issue_entry)

    return {
        "repo": f"{owner}/{repo}",
        "dry_run": dry_run,
        "milestones": milestone_results,
        "issues": issue_results,
        "issue_plan": normalized_plan,
        "create_milestones": create_milestones,
    }


def _build_pending_company_issue_plan(
    *,
    owner: str,
    repo: str,
    issue_plan: list[Any],
    create_milestones: bool,
    apply_policy: CompanyApplyPolicy,
) -> dict[str, Any]:
    normalized_plan: list[dict[str, Any]] = []
    milestones: list[dict[str, Any]] = []
    milestone_seen: set[str] = set()
    issues: list[dict[str, Any]] = []

    for planned_issue in issue_plan:
        source_item_id = str(_issue_field(planned_issue, "source_item_id", ""))
        title = str(_issue_field(planned_issue, "title", ""))
        body = str(_issue_field(planned_issue, "body", ""))
        milestone_name = str(_issue_field(planned_issue, "milestone", ""))
        raw_labels = _issue_field(planned_issue, "labels", [])
        labels = list(raw_labels) if isinstance(raw_labels, list) else []

        normalized_plan.append({
            "source_item_id": source_item_id,
            "title": title,
            "body": body,
            "milestone": milestone_name,
            "labels": labels,
        })

        if milestone_name and milestone_name not in milestone_seen:
            milestone_seen.add(milestone_name)
            milestones.append({
                "title": milestone_name,
                "ensured": False,
                "created": False,
                "status": "awaiting_approval" if create_milestones else "skipped",
            })

        issues.append({
            "source_item_id": source_item_id,
            "title": title,
            "milestone": milestone_name,
            "labels": labels,
            "created": False,
            "url": None,
            "status": "awaiting_approval",
        })

    return {
        "repo": f"{owner}/{repo}",
        "dry_run": False,
        "permission_profile": "team",
        "requires_approval": True,
        "approved": False,
        "approval_status": "pending",
        "milestones": milestones,
        "issues": issues,
        "issue_plan": normalized_plan,
        "create_milestones": create_milestones,
        "apply_policy": apply_policy.model_dump(mode="json"),
    }


def _resolve_company_apply_policy(
    *,
    repo_ref: str,
    issue_plan: list[Any],
    policy_file: Path | None,
) -> CompanyApplyPolicy:
    if policy_file:
        payload = json.loads(policy_file.read_text(encoding="utf-8"))
        return CompanyApplyPolicy.model_validate(payload)
    return derive_policy_from_issue_plan(repo_ref, issue_plan)


def _resolve_apply_policy_for_artifact(
    *,
    artifact: dict[str, Any],
    repo_ref: str,
    issue_plan: list[Any],
    policy_file: Path | None,
) -> tuple[CompanyApplyPolicy, str]:
    if policy_file:
        payload = json.loads(policy_file.read_text(encoding="utf-8"))
        try:
            policy = CompanyApplyPolicy.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Invalid policy file schema: {exc}") from exc
        return policy, f"file:{policy_file}"

    artifact_policy = artifact.get("apply_policy")
    if isinstance(artifact_policy, dict):
        try:
            policy = CompanyApplyPolicy.model_validate(artifact_policy)
        except ValidationError as exc:
            raise ValueError(f"Invalid apply_policy in artifact: {exc}") from exc
        return policy, "artifact"

    return derive_policy_from_issue_plan(repo_ref, issue_plan), "derived"


def _attach_run_metadata(
    payload: dict[str, Any],
    *,
    run_id: str | None,
    artifact_name: str,
) -> None:
    if not run_id:
        return
    payload["run_id"] = run_id
    payload["artifact_name"] = artifact_name
    for key in ("issues", "issue_plan"):
        entries = payload.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                entry["run_id"] = run_id
                entry["artifact_name"] = artifact_name


def _issue_field(issue: Any, key: str, default: Any) -> Any:
    if isinstance(issue, dict):
        return issue.get(key, default)
    return getattr(issue, key, default)


def _fmt_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def _load_model_from_json(path: Path, model_type: type[BaseModel]) -> BaseModel:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return model_type.model_validate(payload)


def _load_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Metrics JSON must be an object.")
    return payload


def _load_run_final_output_payload(output_dir: str, run_id: str) -> dict[str, Any]:
    evidence_store = create_evidence_store(output_dir, run_id, "file")
    final = evidence_store.load_final_output()
    if final:
        return final.model_dump(mode="json")

    artifact = load_company_artifact(output_dir, run_id, "final-output")
    if artifact:
        return artifact

    raise ValueError(f"No final output found for run {run_id}.")


def _emit_artifact(
    artifact: BaseModel | dict[str, Any],
    *,
    output: Path | None,
    run_id: str | None,
    output_dir: str,
    artifact_name: str,
    json_output: bool,
    panel_title: str,
    summary_lines: list[str],
) -> None:
    artifact_json = _artifact_json(artifact)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(artifact_json, encoding="utf-8")

    persisted_path: Path | None = None
    if run_id:
        persisted_path = persist_company_artifact(
            output_dir=output_dir,
            run_id=run_id,
            artifact_name=artifact_name,
            artifact_payload=artifact,
        )

    if json_output:
        click.echo(artifact_json)
        return

    console.print(Panel("\n".join(summary_lines), title=panel_title, border_style="green"))
    if output:
        console.print(f"[green]Artifact written to {output}[/green]")
    if persisted_path:
        console.print(f"[green]Run-linked artifact saved to {persisted_path}[/green]")


def _artifact_json(artifact: BaseModel | dict[str, Any]) -> str:
    if isinstance(artifact, BaseModel):
        return artifact.model_dump_json(indent=2)
    return json.dumps(artifact, indent=2, default=str)


if __name__ == "__main__":
    cli()
