# Contributing

Thanks for contributing to `parallel-agents`.

## Development Setup

1. Install Python 3.11+.
2. Clone the repository.
3. Install dependencies:

```bash
pip install -e ".[dev]"
```

## Local Quality Checks

Run these before opening a pull request:

```bash
python -m ruff check src tests
python -m pytest -q
```

## Pull Request Expectations

- Keep changes scoped to one objective.
- Add or update tests when behavior changes.
- Update `CHANGELOG.md` for user-visible changes.
- Keep CLI and JSON output compatibility in mind (see `COMPATIBILITY.md`).

## Commit Style

Use clear, imperative commit messages, for example:

- `Add parse retry handling to judge agent`
- `Fix npm wrapper Python detection on Windows`

