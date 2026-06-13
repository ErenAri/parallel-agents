# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]

- No changes yet.

## [0.4.4] - 2026-06-13

- Gateway shutdown lifecycle now uses FastAPI lifespan handlers (removes deprecated `on_event` usage).
- CI now includes an evaluation-gate smoke check using `examples/eval_gate_results_example.json`.
- Gateway auth now supports optional JWT HS256 bearer validation:
  - `PA_GATEWAY_JWT_SECRET` / `--jwt-secret`
  - optional issuer check via `PA_GATEWAY_JWT_ISSUER` / `--jwt-issuer`
  - optional audience check via `PA_GATEWAY_JWT_AUDIENCE` / `--jwt-audience`
- Gateway now exposes an MCP-over-HTTP surface and access audit trail:
  - `GET /mcp/tools`
  - `POST /mcp/tools/{tool_name}`
  - `GET /audit/access`
  - write-class MCP tools are policy-gated by `PA_GATEWAY_ALLOW_REMOTE_WRITE_TOOLS` / `--allow-remote-write-tools`
- MCP server now exposes `tool_discovery` for read/write capability discovery and approval-gate metadata.
- Added expanded benchmark fixture: `examples/public_benchmark_v2.json`.
- Added `parallel-agents eval publish` for shareable public benchmark JSON/Markdown snapshots.
- Desktop office improvements:
  - first-run onboarding action shared with `parallel-agents office onboard`
  - project-scoped local gateway start/stop/status controls
  - runs page can route real pipeline execution through the local gateway control plane with fallback
  - worker tiles now prefer structured pipeline trace events over status-string inference
  - project-home summary with recent project picker
  - runs page now executes real pipeline runs
  - live run activity stream and worker status updates during execution
  - artifact compare against previous runs with inline unified diff view
  - artifact browser filters (run/artifact/search) and sorting controls
  - artifact quick actions (`Open File`, `Reveal Folder`, `Export Copy`)
  - release/productivity summary card from eval artifacts (impact, acceptance, regression, gate, cost, duration)
  - metric-history timeline with latest-vs-previous deltas
  - filtered trend view (overall/project/workflow slices, metric/window controls, inline trend rendering)
  - trend export actions for CSV and Markdown reports from selected trend slices/windows
  - graphical trend chart rendering and PNG export from desktop trend controls
  - baseline vs candidate comparison panel with delta metrics and markdown export
  - comparison drill-down sections for workflow/project/case-level deltas
  - case-row evidence navigation links to score/gate/breakdown/results/run artifacts
  - approvals queue filters and approved-plan apply action
  - approvals queue bulk approve/reject actions (selected and visible rows)
  - approvals artifact preview with previous-run diff
  - approvals audit-event drilldown for run/approval history
  - GitHub PR creation flow from desktop with run-linked PR summary artifact, branch suggestions, and generated-patch approval gate
  - desktop company flow `gh auth status` check for preflight GitHub readiness
- Gateway now supports core planner/worker/judge execution through `POST /runs/pipeline`, including persistent status/trace events and a `final-output` artifact.
- Gateway now exposes a local channel-adapter pairing boundary:
  - `POST /channels/slack/events` with Slack signature verification and URL verification
  - `POST /channels/inbound`
  - `POST /channels/pairing/approve`
  - `GET /channels/peers`
  - `parallel-agents gateway channel inbound/approve/peers`
  - unknown senders receive pairing codes and are not processed until approved
- `.gitignore` now excludes local `uv` caches/lockfiles, coverage output, and gateway connector scratch directories.
- Added `parallel-agents office onboard` for local workspace setup, model-readiness reporting, GitHub-readiness reporting, and suggested next actions.
- Workspace knowledge layer v1:
  - `parallel-agents office memory add/list/search/policies`
  - project workspace memory store under `.parallel-agents/memory/`
  - gateway memory endpoints:
    - `POST /memory/entries`
    - `GET /memory/entries`
    - `GET /memory/search`
    - `GET /memory/policies`
    - `PUT /memory/policies`
- Company workflow run-linking improvements:
  - `parallel-agents company pr-create` for draft PR creation from run-linked PR summaries
  - `parallel-agents company pr-link` to persist run-to-PR links
  - `parallel-agents company pr-comment` to post summary/risk comments on existing PRs
  - `parallel-agents company sync-labels` and `parallel-agents company sync-milestones` for template-based GitHub metadata synchronization
  - immutable `pr-link` audit events for linkage traceability
  - `parallel-agents company pr-summary` now persists a run-linked `pr-summary` artifact and markdown file
- Added `parallel-agents release verify` to automate release checklist checks:
  - lint (`ruff check src tests`)
  - tests (`pytest -q`)
  - package build (`python -m build`)
  - CLI help surface checks
  - MCP import check
  - npm wrapper dry-run pack check
  - version parity check across `pyproject.toml`, package `__version__`, and `npm-wrapper/package.json`
- Added `parallel-agents office doctor` for local project-office diagnostics:
  - workspace initialization/directory checks
  - toolchain availability checks (`git`, `gh`, `npm`, `claude`)
  - strict-mode non-zero exit for CI/automation gating
- Added `parallel-agents office fix-setup` for CLI remediation fallback:
  - safe local workspace bootstrap when `.parallel-agents/` is missing
  - post-remediation diagnostics summary
  - actionable follow-up command suggestions (`gh`, `npm`, `claude`, office init)
  - strict-mode non-zero exit when warnings/failures remain
- Desktop project home now displays office-doctor health state with warning/failure counts.
- Desktop Projects page now includes `Run Doctor` and `Fix Setup` actions for one-click setup checks/remediation.

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
