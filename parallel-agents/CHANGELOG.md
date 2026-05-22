# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]

- Gateway shutdown lifecycle now uses FastAPI lifespan handlers (removes deprecated `on_event` usage).
- CI now includes an evaluation-gate smoke check using `examples/eval_gate_results_example.json`.
- Desktop office improvements:
  - project-home summary with recent project picker
  - runs page now executes real pipeline runs
  - live run activity stream and worker status updates during execution
  - artifact compare against previous runs with inline unified diff view
  - approvals queue filters and approved-plan apply action
  - GitHub PR creation flow from desktop with run-linked PR summary artifact

## [0.4.3] - 2026-05-22

### Added
- Gateway queue hardening:
  - run listing endpoint (`GET /runs`)
  - per-run job inspection endpoint (`GET /runs/{run_id}/jobs`)
  - cancel endpoint (`POST /runs/{run_id}/cancel`)
  - retry endpoint (`POST /runs/{run_id}/retry`)
  - metrics summary endpoint (`GET /metrics/summary`)
  - artifact payload endpoint (`GET /runs/{run_id}/artifacts/{artifact_name}`)
  - incremental run lifecycle events for queue execution
- Optional gateway API-key auth for non-local usage:
  - `PA_GATEWAY_API_KEY` environment support
  - `parallel-agents gateway start --api-key ...`
  - header auth via `X-PA-API-Key` or `Authorization: Bearer ...`
- Local desktop/project office foundation:
  - `parallel-agents office init`
  - `parallel-agents office status`
  - `parallel-agents office home`
  - `parallel-agents office artifacts`
  - project-folder workspace under `.parallel-agents/`
  - standalone binary spec includes the project-office module
- New gateway workflow doc: `docs/workflows/gateway-api.md`
- New desktop office workflow doc: `docs/workflows/local-desktop-office.md`
- Evaluation workflow extensions:
  - `parallel-agents eval annotate` to apply per-case annotation updates from JSON
  - `parallel-agents eval sync-pr` to auto-sync acceptance annotations from GitHub PR outcomes
  - `parallel-agents eval sync-ci` to auto-sync regression annotations from CI pass/fail outcomes
  - `parallel-agents eval compare` for baseline/candidate delta reports
  - `parallel-agents eval breakdown` for project/workflow cost and time views
  - `parallel-agents eval gate` for CI threshold enforcement
  - aggregate cost/time summaries in evaluation markdown reports
- Starter public benchmark dataset: `examples/public_benchmark_v1.json`
- Example PR links file: `examples/eval_pr_links_example.json`
- Example CI outcomes file: `examples/eval_ci_outcomes_example.json`

### Changed
- README now documents local project-office usage, gateway endpoints, queue behavior, and auth usage.
- Roadmap and project status pivot Phase 4 from web dashboard to local desktop office.

## [0.4.2] - 2026-05-21

### Added
- Company workflow completion:
  - `SprintPlan` and `PostReleaseReview` models
  - `parallel-agents company sprint`
  - `parallel-agents company post-release`
  - `parallel-agents company templates`
  - `parallel-agents company branch-name`
  - `parallel-agents company pr-summary`
- Approval-gated GitHub issue apply flow with immutable approval audit entries.
- Apply-time policy checks for repository, label, and milestone allowlists/patterns.
- MCP parity tools for company plan, approve, apply, artifacts, templates, and evaluation scoring.
- Optional local gateway/job API:
  - `parallel-agents gateway start`
  - local SQLite project/run/job/event store
  - local company workflow endpoints
- `PROJECT_STATUS.md` checkpoint document.
- Evaluation harness for productivity/effectiveness benchmarking:
  - `parallel-agents eval run` to execute a fixed dataset
  - `parallel-agents eval score` to compute scorecard metrics and delivery impact
- New `src/parallel_agents/eval_harness.py` module with dataset/results models, scoring, and markdown report rendering.
- Example benchmark dataset at `examples/eval_dataset.json`.

### Changed
- README updated with company workflow, evaluation, and gateway usage.
- Roadmap updated to reflect completed, partial, and not-started phases.
- Added robust Claude CLI fallback path in planner/worker/judge query execution when SDK stream parsing fails.

## [0.4.1] - 2026-05-21

### Changed
- Align PyPI release version with npm release `0.4.1`.
- Update package metadata version markers (`pyproject.toml`, `parallel_agents.__version__`).

## [0.4.0] - 2026-05-21

### Added
- Configurable permission mode (`PA_PERMISSION_MODE`) with safe default (`default`).
- Configurable parse retries (`PA_PARSE_RETRY_ATTEMPTS`) for planner, judge, and workers.
- GitHub issue ingestion for planner context via `gh issue view`.
- Patch validation before output and optional explicit patch application mode (`--apply-patch`).
- CLI integration test coverage for `run`, `workers`, `show`, `history`, and `mcp-install`.
- Patch tool tests and expanded pipeline/GitHub happy-path tests.
- Explicit CLI run exit-code matrix for auth/parse/worker/no-patch/apply failures.
- Contributor-facing project docs:
  - `CONTRIBUTING.md`
  - `SECURITY.md`
  - `SUPPORT.md`
  - `.github/CODEOWNERS`
  - `.github/pull_request_template.md`

### Changed
- Cost tracking now records planner/worker/judge usage and reported costs.
- README now includes first-run checklist, run options, strengths/limitations, and exit codes.
- Lint and test hygiene improvements across src/tests.
- Packaging metadata now points to `ErenAri/parallel-agents` and includes organization-friendly project URLs.
- npm wrapper metadata now includes homepage, bugs URL, and provenance-enabled publish config.
- Release workflow now publishes npm with provenance and pinned public access.

## [0.3.0] - 2026-05-20

### Added
- Initial public beta release of `parallel-agents`.
- Parallel multi-agent pipeline (planner -> splitter -> workers -> judge).
- Workers: `security`, `test`, `perf`, `devops`, `arch`, `docs`, `code`, `review`.
- Evidence stores: file-based JSON and SQLite backend.
- CLI commands: `run`, `workers`, `show`, `history`, `init`, `mcp`, `mcp-install`.
- MCP server exposing analysis tools for MCP-compatible coding assistants.
- Packaging and release workflow for PyPI, npm wrapper, and standalone binaries.
- Cross-platform CI and core unit/integration test suite.
