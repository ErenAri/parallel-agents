# Changelog

All notable changes to this project are documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning.

## [Unreleased]

### Added
- Configurable permission mode (`PA_PERMISSION_MODE`) with safe default (`default`).
- Configurable parse retries (`PA_PARSE_RETRY_ATTEMPTS`) for planner, judge, and workers.
- GitHub issue ingestion for planner context via `gh issue view`.
- Patch validation before output and optional explicit patch application mode (`--apply-patch`).
- CLI integration test coverage for `run`, `workers`, `show`, `history`, and `mcp-install`.
- Patch tool tests and expanded pipeline/GitHub happy-path tests.
- Explicit CLI run exit-code matrix for auth/parse/worker/no-patch/apply failures.

### Changed
- Cost tracking now records planner/worker/judge usage and reported costs.
- README now includes first-run checklist, run options, strengths/limitations, and exit codes.
- Lint and test hygiene improvements across src/tests.

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
