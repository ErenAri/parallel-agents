# Roadmap

## Current Product Direction

Build `parallel-agents` into the execution engine for a no-code AI software company workflow.

The near-term product path is:

```text
Stabilize engine -> First-class company workflows -> GitHub approval workflow
  -> Local gateway/job system -> Local desktop office -> Hosted MCP
```

## Phase 0: Engine Stabilization

Status: mostly complete.

Completed:

- CLI, MCP server, PyPI package, npm wrapper, and core worker engine.
- Evidence storage with file and SQLite backends.
- Product vision, PR/FAQ, operating model, quality bar, tech stack policy, and workflow docs.
- Release hygiene docs and compatibility notes.

Remaining:

- Keep package metadata, changelog, README, and examples synchronized for each release.
- Keep release checks repeatable before publishing.

## Phase 1: Company Workflow Models

Status: mostly complete.

Completed:

- `ProductBrief`
- `PRFAQDocument`
- `TechStackDecision`
- `ArchitectureRFC`
- `RoadmapPlan`
- `SprintPlan`
- `ReleaseReadinessReport`
- `PostReleaseReview`
- CLI command group: `parallel-agents company`

Remaining:

- Expand generated artifacts with richer user context and research inputs.
- Add more workflow-specific validation as real users exercise the commands.

## Phase 2: GitHub-First No-Code Workflow

Status: partially complete.

Completed:

- Create issue plans from roadmap artifacts.
- Approval-gated `company plan -> approve -> apply` flow.
- Immutable approval audit log entries.
- Apply-time policy checks for repositories, labels, and milestones.
- GitHub labels/milestones/branch templates.
- Stable branch name generation.
- PR summary generation from stored run outputs.

Remaining:

- Draft PR creation.
- PR summary and risk report comments on GitHub.
- Stronger run-to-issue and run-to-PR linking.
- GitHub label/milestone synchronization commands.

## Phase 3: Gateway and Job System

Status: mostly complete.

Goal: move from one-shot CLI runs to persistent local project sessions.

Completed:

- Optional local gateway dependency group.
- Local FastAPI gateway command.
- SQLite project/run/job/event store.
- Basic company idea, roadmap, plan, approve, apply, artifacts, and events endpoints.
- In-process job queue with persistent run/job status tracking.
- Cancellation and retry controls for queued/failed/policy-blocked runs.
- Run listing and per-run job inspection endpoints.
- Incremental run event stream for enqueue/start/status/complete/cancel.
- Optional API-key protection for non-local gateway exposure.

Remaining:

- Desktop/exe shell integration.
- Hosted-grade auth for multi-tenant remote deployments (OAuth/JWT/session model).

## Phase 4: Local Desktop Office

Status: in progress.

Goal: local `.exe` experience that works inside the selected project folder.

Completed:

- Project-folder workspace layout under `.parallel-agents/`.
- `parallel-agents office init` to create local workspace metadata and directories.
- `parallel-agents office status` to inspect workspace health.
- Desktop project-home summary and recent project picker.
- Desktop approvals queue filters with approved issue-plan apply action.
- Desktop GitHub PR creation with run-linked PR summary artifact.
- Desktop Runs page now executes real pipeline runs with live activity streaming and worker status updates.
- Desktop project-home release/productivity card from eval artifacts (impact, acceptance, regression, gate, cost, duration).
- Desktop metric-history timeline with latest-vs-previous deltas from evaluation score artifacts.
- Desktop filtered trend view (overall/project/workflow slices, date windows, metric selection, inline trend rendering).
- Desktop exportable trend reporting (CSV + Markdown from current filtered view).
- Desktop graphical trend chart rendering with PNG export.
- Desktop cross-run benchmark comparison panel (baseline vs candidate) with delta report export.
- Desktop drill-down analytics in comparison view (workflow/project/case-level change drivers).
- PyInstaller spec includes project-office module for standalone binary builds.

Remaining:

- Workflow navigation into detailed case evidence and artifact links from comparison rows.

## Phase 5: Remote MCP Product Surface

Status: not started.

Goal: use Parallel Agents Office inside Claude, ChatGPT, Codex, Cursor, and similar tools.

Planned deliverables:

- Hosted MCP endpoint.
- OAuth.
- Tool discovery.
- Read-only public tools.
- Write tools behind approval.
- Workspace audit trail.

## Phase 6: Proof and Evaluation

Status: partially complete.

Completed:

- Evaluation dataset format.
- `parallel-agents eval run`.
- `parallel-agents eval score`.
- `parallel-agents eval compare` for baseline vs candidate delta reporting.
- `parallel-agents eval gate` for CI/release threshold enforcement.
- `parallel-agents eval annotate` for run-level acceptance/regression/finding updates.
- `parallel-agents eval sync-pr` for GitHub PR acceptance ingestion.
- `parallel-agents eval sync-ci` for CI outcome regression ingestion.
- `parallel-agents eval breakdown` for cost/time views by project and workflow.
- Scorecards for speed gain, acceptance rate, regression rate, finding precision, and weighted delivery impact.
- Starter public benchmark dataset (`examples/public_benchmark_v1.json`).

Remaining:

- Broader public benchmark dataset coverage.
- PR acceptance tracking is integrated through `eval sync-pr` and PR link files.
- Regression tracking from CI outcomes is integrated through `eval sync-ci`.
- Cost/time views by workflow and project are integrated through `eval breakdown`.

## Near-Term Priority

The next high-impact work is to expand the local desktop office into a practical `.exe` product surface:

- project picker and local workspace home
- artifact browser and approval queue
- GitHub connection and PR flow integration
