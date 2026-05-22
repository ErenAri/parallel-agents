# Project Status

## Current Stage

`parallel-agents` is now more than a parallel code-analysis CLI. It is becoming the engine for **Parallel Agents Office**, a no-code AI software company workflow that moves from idea to release through structured artifacts, approval gates, and measurable quality signals.

The current release line is focused on local, reviewable workflows and a project-folder workspace. Hosted services, OAuth, and web/mobile dashboards are intentionally deferred.

## Implemented

- Parallel specialist worker pipeline with planner, splitter, workers, judge, patches, risk reports, and PR summaries.
- CLI and MCP server surfaces for code review and analysis workflows.
- Evidence storage using file output or SQLite.
- Company workflow artifacts:
  - product brief
  - PR/FAQ
  - tech stack decision
  - architecture RFC
  - roadmap
  - sprint plan
  - release readiness report
  - post-release review
- GitHub-first planning flow:
  - roadmap to issue plan
  - approval-gated apply
  - immutable approval audit log
  - apply-time repo, label, and milestone policy checks
  - branch naming and workflow templates
- Evaluation harness:
  - benchmark dataset execution
  - annotation merge flow for acceptance/regression/finding updates
  - PR-linked acceptance sync (`eval sync-pr`) via GitHub PR state/review decisions
  - CI-linked regression sync (`eval sync-ci`) via case-level pass/fail outcomes
  - scorecard generation
  - baseline vs candidate comparison reports
  - cost/time breakdown reports by project and workflow (`eval breakdown`)
  - CI/release quality gates with threshold checks
  - markdown report output
- Local gateway foundation:
  - FastAPI app behind optional dependency group
  - SQLite project/run/job/event store
  - company idea, roadmap, plan, approve, apply, artifact, and event endpoints
  - in-process queued execution with persistent run/job states
  - run listing plus per-run job inspection
  - cancel and retry controls
  - optional API-key protection for non-local exposure
  - optional JWT HS256 auth with issuer/audience validation
- MCP product-surface foundation:
  - `tool_discovery` output with read/write access classes
  - approval-required metadata for write tools
- Local desktop/project office foundation:
  - `.parallel-agents/` workspace inside a project folder
  - `office init`, `office status`, and `office home` commands
  - `office artifacts` for run-linked artifact inspection
  - workspace directories for runs, artifacts, approvals, audit, and metrics
  - desktop project-home summary with recent project picker
  - desktop Runs page wired to execute real pipeline runs
  - live run activity stream and per-worker status updates in desktop UI
  - artifact compare view against previous runs (inline unified diff)
  - release/productivity summary card in desktop home (impact, acceptance, regression, gate, cost, duration)
  - metric-history timeline with delta vs previous snapshot
  - filtered trend view (overall/project/workflow slices + metric/window controls)
  - trend export actions (CSV and Markdown) from desktop controls
  - graphical trend chart with PNG export for the selected slice/window/metric
  - cross-run baseline vs candidate benchmark comparison panel with markdown export
  - comparison drill-down sections for workflow/project/case-level change drivers
  - case-row evidence navigation links (score/gate/breakdown/results and run artifacts)
  - desktop approvals queue filters and one-click approved issue-plan apply
  - desktop GitHub PR creation flow with run-linked PR summary artifact
  - PyInstaller spec support for the project-office module

## Experimental

- Company workflow artifacts are deterministic scaffolds, not full research-backed product planning yet.
- Gateway is local-only and should bind to `127.0.0.1` by default.
- GitHub write operations require external `gh` authentication and should remain approval-gated.
- Evaluation scores depend on manual annotations for acceptance, regressions, and finding precision.
- Queue worker is in-process/local (single-node), not a distributed job system.

## How To Run Current Workflows

```bash
parallel-agents company idea "Build a no-code repo quality office" --output company/brief.json
parallel-agents company roadmap --brief company/brief.json --output company/roadmap.json
parallel-agents company sprint --roadmap company/roadmap.json --milestone M1 --output company/sprint.json
parallel-agents company plan --roadmap company/roadmap.json --repo owner/repo --no-dry-run --permission-profile team --run-id run-123
parallel-agents company approve --run-id run-123 --approver engineering-lead --approval-note "Reviewed"
parallel-agents company apply --run-id run-123
```

```bash
parallel-agents office init --project . --name "Project Name"
parallel-agents office status --project .
parallel-agents office home --project .
parallel-agents office artifacts --project .
```

```bash
parallel-agents gateway start --host 127.0.0.1 --port 8733

# optional auth for non-local use (API key)
set PA_GATEWAY_API_KEY=my-secret
parallel-agents gateway start --host 0.0.0.0 --port 8733

# optional auth for non-local use (JWT HS256)
set PA_GATEWAY_JWT_SECRET=replace-with-shared-secret
set PA_GATEWAY_JWT_ISSUER=parallel-agents
set PA_GATEWAY_JWT_AUDIENCE=parallel-agents-office
parallel-agents gateway start --host 0.0.0.0 --port 8733
```

## Known Limitations

- Desktop GUI is available but still maturing (single-user local workflow focus).
- No hosted MCP endpoint or OAuth yet.
- No distributed/remote worker execution beyond the current local in-process queue.
- No hosted-grade OAuth/session model yet (local API key and JWT HS256 are available).
- No automated GitHub PR comments in this checkpoint.
- Package publishing is still manual and should only happen after release checks pass.

## Next Milestone

Expand the local desktop office into a full `.exe` product surface:

- project picker and local workspace home
- artifact browser and approval queue
- GitHub connect + repository integration
- PR creation and review actions from the local office
- richer release and productivity views
