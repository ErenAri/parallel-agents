# Project Status

## Current Stage

`parallel-agents` is now more than a parallel code-analysis CLI. It is becoming the engine for **Parallel Agents Office**, a no-code AI software company workflow that moves from idea to release through structured artifacts, approval gates, and measurable quality signals.

The current release line is focused on local, reviewable workflows. Hosted services, OAuth, and a full dashboard are intentionally deferred until the local gateway is stable.

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
  - scorecard generation
  - markdown report output
- Local gateway foundation:
  - FastAPI app behind optional dependency group
  - SQLite project/run/job/event store
  - company idea, roadmap, plan, approve, apply, artifact, and event endpoints

## Experimental

- Company workflow artifacts are deterministic scaffolds, not full research-backed product planning yet.
- Gateway is local-only and should bind to `127.0.0.1` by default.
- GitHub write operations require external `gh` authentication and should remain approval-gated.
- Evaluation scores depend on manual annotations for acceptance, regressions, and finding precision.

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
parallel-agents gateway start --host 127.0.0.1 --port 8733
```

## Known Limitations

- No full no-code dashboard yet.
- No hosted MCP endpoint or OAuth yet.
- No background queue worker beyond the current local job records.
- No automated GitHub PR creation/commenting in this checkpoint.
- Package publishing is still manual and should only happen after release checks pass.

## Next Milestone

Harden the local gateway/job system:

- add background queue execution
- add cancellation/retry support
- stream run events
- connect gateway state to future UI
- keep write actions behind approval and policy gates
