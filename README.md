# parallel-agents

A parallel multi-agent pipeline for code analysis and transformation, powered by Claude.

Fan out code analysis to 8 specialist AI agents running concurrently, then merge results into a unified report with patches, risk assessments, and PR summaries.

## Product Direction

`parallel-agents` is the execution engine for **Parallel Agents Office**: a no-code AI software company workflow that can take a project from idea to release.

The long-term product goal is to coordinate specialist agents across the full software lifecycle:

```text
Idea -> PR/FAQ -> Tech stack decision -> Architecture RFC -> Roadmap
     -> Sprint -> Implementation -> Review -> Release -> Learning
```

The current package focuses on the engine plus local workflow orchestration: CLI, MCP server, specialist workers, evidence storage, patch generation, evaluation metrics, and a local gateway/job system with queueing, retry/cancel controls, and optional API-key protection.

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
parallel-agents eval score --results eval/results.json --output-report eval/report.md --output-json eval/score.json

# Build company workflow artifacts
parallel-agents company idea "Build a no-code repo quality office" --output company/brief.json
parallel-agents company stack --repo ./my-project --output company/stack.json
parallel-agents company roadmap --brief company/brief.json --output company/roadmap.json
parallel-agents company sprint --roadmap company/roadmap.json --milestone M1 --output company/sprint.json
parallel-agents company plan --roadmap company/roadmap.json --repo owner/repo --dry-run --output company/issue-plan.json
parallel-agents company release-check --repo ./my-project --output company/release-check.json
parallel-agents company post-release --release-id v0.4.2 --release-check company/release-check.json --output company/post-release.json
parallel-agents company templates --roadmap company/roadmap.json --output company/templates.json
parallel-agents company branch-name --issue RM-01 --title "Define product and workflow artifacts"
parallel-agents company artifacts --run-id run-123

# Team-gated write flow (approval required before GitHub issue creation)
parallel-agents company plan --roadmap company/roadmap.json --repo owner/repo --no-dry-run --permission-profile team --run-id run-123
parallel-agents company approve --run-id run-123 --approver engineering-lead --approval-note "Reviewed and approved for sprint kickoff"
parallel-agents company apply --run-id run-123

# Optional explicit policy override at apply time
parallel-agents company apply --run-id run-123 --policy-file company/apply-policy.json

# Local gateway for future no-code surfaces
parallel-agents gateway start --host 127.0.0.1 --port 8733

# Optional API key protection (recommended when binding beyond localhost)
set PA_GATEWAY_API_KEY=my-secret
parallel-agents gateway start --host 0.0.0.0 --port 8733

# or explicit key via CLI
parallel-agents gateway start --api-key my-secret
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
| `parallel-agents eval run/score` | Run and score productivity/effectiveness benchmarks |
| `parallel-agents gateway start` | Start the local project/run/job API |

## Gateway API

The local gateway exposes a persistent API for projects, runs, jobs, artifacts, and audit events.

- `GET /health`
- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `POST /runs/company/idea`
- `POST /runs/company/roadmap`
- `POST /runs/company/plan`
- `POST /runs/company/approve`
- `POST /runs/company/apply`
- `GET /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/cancel`
- `POST /runs/{run_id}/retry`
- `GET /runs/{run_id}/jobs`
- `GET /runs/{run_id}/artifacts`
- `GET /runs/{run_id}/events`

Run endpoints support:

- synchronous mode by default (`wait=true`)
- async enqueue mode (`wait=false`)
- custom wait timeout (`wait_timeout_seconds`)

When `PA_GATEWAY_API_KEY` or `--api-key` is set, requests require either:

- `X-PA-API-Key: <key>`, or
- `Authorization: Bearer <key>`

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
- Optional local gateway for persistent project/run state.

## Current Limitations

- Generated patches should be reviewed before applying.
- GitHub issue mode requires `gh` installation and authentication.
- Output quality still depends on model behavior and repository context quality.
- Gateway binds to localhost by default; non-local exposure should use API-key protection at minimum.

## Evaluation Harness

Use the built-in evaluation flow to measure productivity and effectiveness over a fixed benchmark set.

1. Create or edit a dataset JSON (see `examples/eval_dataset.json`).
2. Run benchmark execution:

```bash
parallel-agents eval run \
  --dataset examples/eval_dataset.json \
  --repo-root . \
  --output eval/results.json
```

3. Fill manual annotation fields in `eval/results.json` per case:
   - `accepted_without_major_edits`
   - `introduced_regression`
   - `findings_true_positives`
   - `findings_false_positives`
   - `reviewer_minutes`
4. Compute score and report:

```bash
parallel-agents eval score \
  --results eval/results.json \
  --output-json eval/score.json \
  --output-report eval/report.md
```

Scoring includes:
- speed gain vs baseline human minutes
- acceptance rate and gain vs baseline
- regression rate and increase vs baseline
- finding precision
- weighted delivery impact score:
  `0.4*speed_gain + 0.4*acceptance_gain - 0.2*regression_increase`

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
