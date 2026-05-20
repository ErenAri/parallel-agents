# parallel-agents

A parallel multi-agent pipeline for code analysis and transformation, powered by Claude.

Fan out code analysis to 8 specialist AI agents running concurrently, then merge results into a unified report with patches, risk assessments, and PR summaries.

## Architecture

```
User Task / GitHub Issue / Repo
        ↓
   Planner Agent (analyzes repo, creates task plan)
        ↓
   Task Splitter (dependency resolution, batch grouping)
        ↓
   Parallel Workers (asyncio fan-out)
    ┌──────────┬──────────┬──────────┬──────────┐
    │ Security │ Test     │ Perf     │ DevOps   │
    │ Arch     │ Docs     │ Code     │ Review   │
    └──────────┴──────────┴──────────┴──────────┘
        ↓
   Evidence Store (JSON / SQLite)
        ↓
   Judge Agent (merge, resolve conflicts, produce patch)
        ↓
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

Download from [GitHub Releases](https://github.com/ErenAri/pa/releases) — no Python required.

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
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `parallel-agents run <task>` | Run the pipeline |
| `parallel-agents workers` | List available workers |
| `parallel-agents show <run-id>` | View results of a previous run |
| `parallel-agents history` | List all previous runs |
| `parallel-agents init` | Generate default configuration |

### Run Options

| Flag | Description |
|------|-------------|
| `--repo, -r` | Path to repository |
| `--workers, -w` | Comma-separated workers to enable |
| `--disable-workers, -d` | Comma-separated workers to disable |
| `--output, -o` | Output format: `rich`, `json`, `patch` |
| `--model, -m` | Override model for all agents |
| `--store, -s` | Evidence store: `file` or `sqlite` |
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
export PA_MAX_PARALLEL_WORKERS=4
export PA_STORE_BACKEND=sqlite
```

## Requirements

- Python 3.11+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- An Anthropic API key (via Claude Code authentication)

## License

MIT
