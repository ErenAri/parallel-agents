# Roadmap

## Current Product Direction

Build `parallel-agents` into the execution engine for a no-code AI software company workflow.

The near-term product path is:

```text
Stabilize engine -> First-class company workflows -> GitHub approval workflow
  -> Local gateway/job system -> No-code dashboard -> Hosted MCP
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

- Gateway-backed UI integration.
- Hosted-grade auth for multi-tenant remote deployments (OAuth/JWT/session model).

## Phase 4: No-Code Web Dashboard

Status: not started.

Goal: public-facing workflow for non-coders.

Planned deliverables:

- Connect GitHub.
- Choose repository.
- Start project from idea.
- Review generated artifacts.
- Approve implementation.
- Watch agent runs.
- Open PR.
- View metrics.

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
- Scorecards for speed gain, acceptance rate, regression rate, finding precision, and weighted delivery impact.

Remaining:

- Public benchmark dataset.
- Run comparison reports.
- PR acceptance tracking.
- Regression tracking from CI outcomes.
- Cost and time dashboard.

## Near-Term Priority

The next high-impact work is **Phase 4: No-Code Web Dashboard** backed by the current gateway APIs.

The gateway now provides persistent runs, job state, artifacts, events, retry/cancel controls, and basic API-key protection, which is enough to start a practical UI without a backend rewrite.
