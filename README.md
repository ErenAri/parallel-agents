# Parallel Agents Office

**The AI software company OS — declare your agent org as code, fork it, and watch it run.**

Powered by Claude, Parallel Agents Office runs a *company of AI agents* over your codebase: specialist workers (security, test, perf, devops, arch, docs, code, review) fan out concurrently, then a judge merges their work into a unified report with patches, risk assessments, and PR summaries. The engine ships as the `parallel-agents` package.

## Product Direction

**Parallel Agents Office** is a no-code **AI software company OS**: bring a project idea, and a coordinated org of AI agents runs discovery, planning, architecture, implementation, review, and release. The `parallel-agents` package is its execution engine.

The thesis (after Andrej Karpathy's "org code"): an organization is just a *topology + rules* for how nodes communicate, decide, and escalate — so it can be written as code, **forked, diffed, and mutated** — and made fully **legible**, so a human conductor can zoom from the whole-org graph down to a single agent's live token stream. Parallel Agents Office is that idea, local-first and reviewable.

The long-term product goal is to coordinate specialist agents across the full software lifecycle:

```text
Idea -> PR/FAQ -> Tech stack decision -> Architecture RFC -> Roadmap
     -> Sprint -> Implementation -> Review -> Release -> Learning
```

The current package focuses on a local-first project office: CLI, standalone binary packaging, MCP server, specialist workers, evidence storage, patch generation, evaluation metrics, and a project-folder workspace under `.parallel-agents/`.

## Architecture

```text
User Task / GitHub Issue / Repo
  |
Planner Agent (analyzes repo, creates task plan)
  |
Task Splitter (dependency resolution, batch grouping)
  |
Parallel Workers (asyncio fan-out):
  security, test, perf, devops, arch, docs, code, review
  |
Evidence Store (JSON / SQLite)
  |
Judge Agent (merge, resolve conflicts, produce patch)
  |
Final Output (patch + PR summary + risk report)
```

## Installation

### From PyPI

```bash
pip install parallel-agents
# or with pipx for isolated CLI
pipx install parallel-agents
```

### From npm (wrapper)

```bash
npx parallel-agents run --repo ./my-project "Fix security issues"
```

### Standalone binary

Download from [GitHub Releases](https://github.com/ErenAri/parallel-agents/releases) - no Python required.

## First Run Checklist

1. Install package with `pip install parallel-agents`.
2. Install Claude Code CLI and complete authentication.
3. If using GitHub issue URLs, install GitHub CLI and run `gh auth login`.
4. Run `parallel-agents workers` to verify worker config.
5. Run `parallel-agents run --repo ./my-project "Review for security and quality issues"`.

## Quick Start

```bash
# Analyze a local repo
parallel-agents run --repo ./my-project "Fix security issues and improve code quality"

# From a GitHub issue
parallel-agents run "https://github.com/org/repo/issues/42" --repo ./local-clone

# Select specific workers
parallel-agents run --workers security,code,review "Refactor the auth module"

# Use SQLite evidence store
parallel-agents run --store sqlite --repo ./project "Add input validation"

# Output as JSON or patch
parallel-agents run --output json --repo ./project "Fix bugs"
parallel-agents run --output patch --repo ./project "Fix bugs" > fix.patch

# Run a benchmark dataset
parallel-agents eval run --dataset examples/eval_dataset.json --repo-root .
parallel-agents eval annotate --results eval/results.json --annotations eval/annotations.json --in-place
parallel-agents eval sync-pr --results eval/results.json --links eval/pr_links.json --in-place
parallel-agents eval sync-ci --results eval/results.json --outcomes eval/ci_outcomes.json --in-place
parallel-agents eval score --results eval/results.json --output-report eval/report.md --output-json eval/score.json
parallel-agents eval compare --baseline-results eval/baseline-results.json --candidate-results eval/results.json --output-report eval/compare.md --output-json eval/compare.json
parallel-agents eval breakdown --results eval/results.json --output-report eval/breakdown.md --output-json eval/breakdown.json
parallel-agents eval publish --results eval/results.json --baseline-results eval/baseline-results.json --label release-0.4.4-rc1 --output-json eval/public-benchmark.json --output-report eval/public-benchmark.md
parallel-agents eval gate --results eval/results.json --min-weighted-impact 0.05 --max-regression-rate 0.10 --min-acceptance-rate 0.70
parallel-agents release verify --project-root . --json-output

# Build company workflow artifacts
parallel-agents company idea "Build a no-code repo quality office" --output company/brief.json
parallel-agents company stack --repo ./my-project --output company/stack.json
parallel-agents company roadmap --brief company/brief.json --output company/roadmap.json
parallel-agents company sprint --roadmap company/roadmap.json --milestone M1 --output company/sprint.json
parallel-agents company plan --roadmap company/roadmap.json --repo owner/repo --dry-run --output company/issue-plan.json
parallel-agents company release-check --repo ./my-project --output company/release-check.json
parallel-agents company post-release --release-id v0.4.4 --release-check company/release-check.json --output company/post-release.json
parallel-agents company templates --roadmap company/roadmap.json --output company/templates.json
parallel-agents company sync-labels --repo owner/repo --roadmap company/roadmap.json --dry-run
parallel-agents company sync-milestones --repo owner/repo --roadmap company/roadmap.json --dry-run
parallel-agents company branch-name --issue RM-01 --title "Define product and workflow artifacts"
parallel-agents company pr-create --run-id run-123 --head feature/run-123 --repo owner/repo --draft
parallel-agents company pr-link --run-id run-123 --pr-url https://github.com/owner/repo/pull/42
parallel-agents company pr-comment --run-id run-123 --pr-url https://github.com/owner/repo/pull/42 --mode both
parallel-agents company artifacts --run-id run-123

# Team-gated write flow (approval required before GitHub issue creation)
parallel-agents company plan --roadmap company/roadmap.json --repo owner/repo --no-dry-run --permission-profile team --run-id run-123
parallel-agents company approve --run-id run-123 --approver engineering-lead --approval-note "Reviewed and approved for sprint kickoff"
parallel-agents company apply --run-id run-123

# Optional explicit policy override at apply time
parallel-agents company apply --run-id run-123 --policy-file company/apply-policy.json

# Initialize a project-folder office workspace
parallel-agents office onboard --project ./my-project --name "My Project"
parallel-agents office init --project ./my-project --name "My Project"
parallel-agents office status --project ./my-project
parallel-agents office doctor --project ./my-project
parallel-agents office fix-setup --project ./my-project
parallel-agents office home --project ./my-project
parallel-agents office artifacts --project ./my-project
parallel-agents office artifacts --project ./my-project --run-id run-123
parallel-agents office artifacts --project ./my-project --run-id run-123 --artifact roadmap
parallel-agents office memory add --project ./my-project --kind decision --title "Choose stack" --content "Python + FastAPI + local SQLite"
parallel-agents office memory list --project ./my-project
parallel-agents office memory search --project ./my-project --query "FastAPI"
parallel-agents office memory policies --project ./my-project

# Internal local gateway/job API
parallel-agents gateway start --host 127.0.0.1 --port 8733

# Optional API key protection (recommended when binding beyond localhost)
set PA_GATEWAY_API_KEY=my-secret
parallel-agents gateway start --host 0.0.0.0 --port 8733

# or explicit key via CLI
parallel-agents gateway start --api-key my-secret

# Optional JWT HS256 protection
set PA_GATEWAY_JWT_SECRET=replace-with-shared-secret
set PA_GATEWAY_JWT_ISSUER=parallel-agents
set PA_GATEWAY_JWT_AUDIENCE=parallel-agents-office
parallel-agents gateway start --host 0.0.0.0 --port 8733

# or explicit JWT flags via CLI
parallel-agents gateway start --jwt-secret replace-with-shared-secret --jwt-issuer parallel-agents --jwt-audience parallel-agents-office

# Optional remote MCP write enablement over gateway /mcp endpoints
set PA_GATEWAY_ALLOW_REMOTE_WRITE_TOOLS=1
parallel-agents gateway start --allow-remote-write-tools

# Optional Slack Events connector
set PA_GATEWAY_SLACK_SIGNING_SECRET=xox-signing-secret
parallel-agents gateway start --slack-signing-secret xox-signing-secret

# Channel pairing adapter
parallel-agents gateway channel inbound --channel slack --peer-id U123 --message "Review this repo" --execute
parallel-agents gateway channel approve --code ABC123 --approved-by operator
parallel-agents gateway channel peers --channel slack
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `parallel-agents run <task>` | Run the pipeline |
| `parallel-agents workers` | List available workers |
| `parallel-agents show <run-id>` | View results of a previous run |
| `parallel-agents history` | List all previous runs |
| `parallel-agents init` | Generate default configuration |
| `parallel-agents company ...` | Generate company workflow artifacts (brief, stack, RFC, roadmap, issue plan, release checks) |
| `parallel-agents office ...` | Create and inspect a local `.parallel-agents/` project workspace |
| `parallel-agents eval run/annotate/sync-pr/sync-ci/score/compare/breakdown/publish/gate` | Run, annotate, auto-sync PR acceptance and CI regressions, score, compare, break down cost/time, publish benchmark snapshots, and quality-gate productivity/effectiveness benchmarks |
| `parallel-agents release verify` | Run consolidated release checklist checks (lint/tests/build/help/mcp/npm/version parity) |
| `parallel-agents gateway start` | Start the local project/run/job API |
| `parallel-agents gateway channel inbound/approve/peers` | Exercise local inbound-channel pairing and peer allowlist workflows |

## Local Project Office

The product direction is local `.exe` first. A project workspace lives inside the repository or project folder:

```text
my-project/
  .parallel-agents/
    project.json
    runs/
    artifacts/
    approvals/
    audit/
    metrics/
    memory/
```

Initialize it with:

```bash
parallel-agents office onboard --project ./my-project --name "My Project"
parallel-agents office init --project ./my-project --name "My Project"
parallel-agents office status --project ./my-project
parallel-agents office doctor --project ./my-project --strict
parallel-agents office fix-setup --project ./my-project --strict
parallel-agents office home --project ./my-project
parallel-agents office artifacts --project ./my-project
```

Desktop Office (`parallel-agents-desktop`) now includes:
- project home summary with recent project picker
- workspace doctor status signal (healthy/attention + warning/failure counts)
- first-run onboarding action for workspace setup, model readiness, and GitHub readiness
- desktop-owned local gateway controls for start/stop/status
- live pipeline run execution through the local gateway when available, with in-process fallback
- event-native worker status updates from structured pipeline traces, with text-status fallback
- artifact compare against previous runs (inline unified diff)
- artifact browser search/filter/sort controls by run and artifact type
- artifact quick actions (open file, reveal folder, export copy)
- release/productivity summary from eval artifacts (impact, acceptance, regression, gate, cost, duration)
- metric-history timeline with latest-vs-previous deltas
- filtered trend view (overall/project/workflow slices, metric picker, date window)
- trend export from desktop (CSV and Markdown report)
- graphical chart rendering with chart image export (PNG)
- cross-run baseline vs candidate comparison with delta report export
- comparison drill-down by workflow, project, and case-level changes
- case-row evidence links to underlying score/gate/breakdown/results/run artifacts
- approvals queue with status filters, bulk approve/reject, artifact diff preview, and audit-event drilldown
- company workflow steps through issue-plan apply
- GitHub PR creation from run context with suggested branch names and generated PR summary markdown
- generated patches require approval of the exact `final-output` artifact before PR creation
- built-in `gh auth status` check from the Company flow before live GitHub writes

The gateway remains an internal job API for local automation and desktop shells. It is not the primary product UI. The desktop can start/stop a project-scoped gateway for the current session. Set `PA_DESKTOP_GATEWAY_URL` or leave `PA_DESKTOP_USE_GATEWAY=auto` to let the desktop use `http://127.0.0.1:8733` when it is running; set `PA_DESKTOP_GATEWAY_REQUIRED=1` to fail instead of falling back to in-process runs.

## Gateway API

The local gateway exposes a persistent API for projects, runs, jobs, artifacts, and audit events.

- `GET /health`
- `GET /metrics/summary`
- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `POST /memory/entries`
- `GET /memory/entries`
- `GET /memory/search`
- `GET /memory/policies`
- `PUT /memory/policies`
- `POST /runs/pipeline`
- `POST /channels/slack/events`
- `POST /channels/inbound`
- `POST /channels/pairing/approve`
- `GET /channels/peers`
- `POST /runs/company/idea`
- `POST /runs/company/roadmap`
- `POST /runs/company/plan`
- `POST /runs/company/approve`
- `POST /runs/company/apply`
- `GET /mcp/tools`
- `POST /mcp/tools/{tool_name}`
- `GET /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/cancel`
- `POST /runs/{run_id}/retry`
- `GET /runs/{run_id}/jobs`
- `GET /runs/{run_id}/artifacts/{artifact_name}`
- `GET /runs/{run_id}/artifacts`
- `GET /runs/{run_id}/events`
- `GET /audit/access`

Run endpoints support:

- synchronous mode by default (`wait=true`)
- async enqueue mode (`wait=false`)
- custom wait timeout (`wait_timeout_seconds`)

When `PA_GATEWAY_API_KEY` or `--api-key` is set, requests require either:

- `X-PA-API-Key: <key>`, or
- `Authorization: Bearer <key>`

When `PA_GATEWAY_JWT_SECRET` or `--jwt-secret` is set, requests may also use:

- `Authorization: Bearer <jwt>`

Optional issuer/audience constraints:

- `PA_GATEWAY_JWT_ISSUER` or `--jwt-issuer`
- `PA_GATEWAY_JWT_AUDIENCE` or `--jwt-audience`
- `PA_GATEWAY_ALLOW_REMOTE_WRITE_TOOLS` or `--allow-remote-write-tools` to allow write-class MCP tools via gateway.

`/health` remains readable without auth for liveness checks.

### Run Options

| Flag | Description |
|------|-------------|
| `--repo, -r` | Path to repository |
| `--workers, -w` | Comma-separated workers to enable |
| `--disable-workers, -d` | Comma-separated workers to disable |
| `--output, -o` | Output format: `rich`, `json`, `patch` |
| `--model, -m` | Override model for all agents |
| `--permission-mode` | Override permission mode: `default`, `acceptEdits`, `plan`, `bypassPermissions` |
| `--store, -s` | Evidence store: `file` or `sqlite` |
| `--apply-patch` | Apply generated patch to repo via `git apply` (explicit opt-in) |
| `--streaming/--no-streaming` | Toggle live progress display |

## Programmatic Usage

```python
import asyncio
from parallel_agents import Pipeline, PipelineConfig
from parallel_agents.config import WorkerConfig

config = PipelineConfig(
    workers={
        "security": WorkerConfig(enabled=True),
        "code": WorkerConfig(enabled=True, model="opus"),
        "review": WorkerConfig(enabled=True),
    },
    max_parallel_workers=3,
)

async def main():
    pipeline = Pipeline(config)
    result = await pipeline.run(
        "Review for security issues",
        repo_path="./my-project",
    )
    print(result.summary)
    if result.patch:
        print(result.patch)

asyncio.run(main())
```

## Workers

| Worker | Focus Area |
|--------|-----------|
| **security** | OWASP Top 10, dependency vulns, secret scanning |
| **test** | Coverage gaps, edge cases, test generation |
| **perf** | Complexity analysis, N+1 queries, bottlenecks |
| **devops** | CI/CD, Docker, deployment configuration |
| **arch** | SOLID principles, design patterns, coupling |
| **docs** | README, docstrings, API documentation |
| **code** | Implementation, refactoring (uses Opus) |
| **review** | Code style, best practices, anti-patterns |

## Configuration

Set via environment variables (prefix `PA_`), `.env` file, or programmatically:

```bash
export PA_PLANNER_MODEL=opus
export PA_JUDGE_MODEL=opus
export PA_PERMISSION_MODE=default
export PA_PARSE_RETRY_ATTEMPTS=1
export PA_MAX_PARALLEL_WORKERS=4
export PA_STORE_BACKEND=sqlite
```

`PA_PERMISSION_MODE` supports `default`, `acceptEdits`, `plan`, and `bypassPermissions`.

## Current Strengths

- Parallel specialist analysis with a single merged result.
- CLI, MCP server, PyPI package, npm wrapper, and release workflows.
- Evidence storage for run history (`file` or `sqlite`).
- Company workflow artifacts from idea intake through post-release review.
- Approval-gated GitHub issue planning with apply-time policy checks.
- Local `.parallel-agents/` project workspace for desktop/exe-first usage.
- Local workspace memory layer for decisions, lessons learned, and policy guardrails.
- Optional local gateway for persistent project/run state with API key or JWT auth.
- MCP tool discovery payload (`tool_discovery`) for read/write capability and approval metadata.

## Current Limitations

- Generated patches should be reviewed before applying.
- GitHub issue mode requires `gh` installation and authentication.
- Output quality still depends on model behavior and repository context quality.
- Gateway binds to localhost by default; non-local exposure should use API-key protection at minimum.
- No web dashboard is shipped; the product direction is local project-folder tooling.

## Evaluation Harness

Use the built-in evaluation flow to measure productivity and effectiveness over a fixed benchmark set.

1. Create or edit a dataset JSON (see `examples/eval_dataset.json`).
   You can also start from `examples/public_benchmark_v1.json` or `examples/public_benchmark_v2.json`.
2. Run benchmark execution:

```bash
parallel-agents eval run \
  --dataset examples/eval_dataset.json \
  --repo-root . \
  --output eval/results.json
```

3. Apply per-case annotations (acceptance, regressions, findings, reviewer time):

```bash
parallel-agents eval annotate \
  --results eval/results.json \
  --annotations eval/annotations.json \
  --in-place
```

`eval/annotations.json` format:

```json
[
  {
    "case_id": "SEC-001",
    "accepted_without_major_edits": true,
    "introduced_regression": false,
    "findings_true_positives": 4,
    "findings_false_positives": 1,
    "reviewer_minutes": 12
  }
]
```

You can copy from `examples/eval_annotations_example.json`.

4. Compute score and report:

```bash
parallel-agents eval score \
  --results eval/results.json \
  --output-json eval/score.json \
  --output-report eval/report.md

# Compare candidate run vs baseline
parallel-agents eval compare \
  --baseline-results eval/baseline-results.json \
  --candidate-results eval/results.json \
  --output-json eval/compare.json \
  --output-report eval/compare.md

# CI gate (non-zero exit code when thresholds fail)
parallel-agents eval gate \
  --results eval/results.json \
  --min-weighted-impact 0.05 \
  --max-regression-rate 0.10 \
  --min-acceptance-rate 0.70 \
  --min-finding-precision 0.75

parallel-agents eval breakdown \
  --results eval/results.json \
  --output-json eval/breakdown.json \
  --output-report eval/breakdown.md
```

Optional PR acceptance sync from GitHub:

```bash
parallel-agents eval sync-pr \
  --results eval/results.json \
  --links eval/pr_links.json \
  --in-place
```

`eval/pr_links.json` format:

```json
[
  {
    "case_id": "SEC-001",
    "pr_url": "https://github.com/org/repo/pull/123"
  }
]
```

You can copy from `examples/eval_pr_links_example.json`.

Optional CI regression sync:

```bash
parallel-agents eval sync-ci \
  --results eval/results.json \
  --outcomes eval/ci_outcomes.json \
  --in-place
```

`eval/ci_outcomes.json` format:

```json
[
  {
    "case_id": "SEC-001",
    "ci_passed": false,
    "source": "github-actions"
  }
]
```

You can copy from `examples/eval_ci_outcomes_example.json`.

CI gate smoke fixture is available at `examples/eval_gate_results_example.json`.

Scoring includes:
- speed gain vs baseline human minutes
- acceptance rate and gain vs baseline
- regression rate and increase vs baseline
- finding precision
- weighted delivery impact score:
  `0.4*speed_gain + 0.4*acceptance_gain - 0.2*regression_increase`

`eval gate` returns non-zero when thresholds fail, so it can be used in CI/release gates.

## Project Docs

- [VISION.md](VISION.md)
- [PRFAQ.md](PRFAQ.md)
- [PROJECT_STATUS.md](PROJECT_STATUS.md)
- [OPERATING_MODEL.md](OPERATING_MODEL.md)
- [QUALITY_BAR.md](QUALITY_BAR.md)
- [TECH_STACK_POLICY.md](TECH_STACK_POLICY.md)
- [ROADMAP.md](ROADMAP.md)
- [docs/workflows/idea-to-release.md](docs/workflows/idea-to-release.md)
- [docs/workflows/agent-roles.md](docs/workflows/agent-roles.md)
- [docs/workflows/local-desktop-office.md](docs/workflows/local-desktop-office.md)
- [docs/workflows/gateway-api.md](docs/workflows/gateway-api.md)
- [CHANGELOG.md](CHANGELOG.md)
- [COMPATIBILITY.md](COMPATIBILITY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [SUPPORT.md](SUPPORT.md)

## Exit Codes

- `0`: success
- `1`: runtime failure
- `2`: authentication/API key failure
- `3`: parse failure in planner/judge/worker structured output
- `4`: worker execution failure (`status=error`)
- `5`: no patch available when patch output/apply is requested
- `6`: patch apply/check failure

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- [GitHub CLI](https://cli.github.com/) installed and authenticated for GitHub issue URL mode
- An Anthropic API key (via Claude Code authentication)

## License

MIT
