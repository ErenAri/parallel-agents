# parallel-agents

Parallel multi-agent pipeline for code analysis and transformation, powered by Claude.

This is the **npm wrapper** for the Python `parallel-agents` package. It auto-installs the Python package and delegates all commands to it.

## Prerequisites

- **Python 3.11+** must be installed and on your PATH
- **Claude Code CLI** must be installed and authenticated

## Usage

```bash
# Via npx (no install needed)
npx parallel-agents run --repo ./my-project "Fix security issues"

# Or install globally
npm install -g parallel-agents
parallel-agents run --repo ./project "Review code quality"
parallel-agents workers
```

## How it works

This package is a thin Node.js wrapper that:
1. Checks for Python 3.11+
2. Installs `parallel-agents` from PyPI if not present
3. Forwards all CLI arguments to the Python CLI

For full documentation, see the [Python package on PyPI](https://pypi.org/project/parallel-agents/).
