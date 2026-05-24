# Compatibility Policy

This document defines what is considered stable for `parallel-agents` and what may change between versions.

## Stable In v1.x

The following are compatibility-sensitive once `1.0.0` is released:

- CLI command names:
  - `run`
  - `workers`
  - `show`
  - `history`
  - `init`
  - `eval run`
  - `eval score`
  - `gateway start`
  - `mcp`
  - `mcp-install`
  - `company idea`
  - `company prfaq`
  - `company stack`
  - `company rfc`
  - `company roadmap`
  - `company sprint`
  - `company release-check`
  - `company post-release`
  - `company plan`
  - `company approve`
  - `company apply`
  - `company templates`
  - `company branch-name`
  - `company pr-summary`
  - `company artifacts`
- MCP tool names:
  - `review`
  - `security_scan`
  - `test_analysis`
  - `perf_analysis`
  - `code_review`
  - `analyze`
  - `list_workers`
  - company workflow tools
  - evaluation scoring tool
- Core Python API exports from `parallel_agents.__init__`:
  - `Pipeline`
  - `PipelineConfig`
  - model/data classes currently exported
- High-level JSON output structure from CLI `run --output json`:
  - `summary`
  - `risk_report`
  - `patch`
  - `pr_summary`
  - `worker_results`
  - `conflicts_resolved`
  - `metadata`

## Best-Effort Fields

These fields are not strictly stable and may evolve:

- Prompt-derived natural language text (`summary`, `pr_summary`, finding descriptions).
- Model- and SDK-specific telemetry in `metadata` and token usage dictionaries.
- Additional metadata keys related to retries, patch validation, and diagnostics.

## Pre-1.0 Rules

Before `1.0.0`:

- Minor versions may include behavior changes and output-shape refinements.
- Breaking changes are still documented in `CHANGELOG.md`.
- CLI command names and MCP tool names should be treated as high-priority stability targets, but are not yet guaranteed.

## Deprecation Approach

When a stable interface must change:

- Mark it as deprecated in release notes.
- Keep backward-compatible behavior for at least one minor release when practical.
- Provide migration guidance with concrete before/after examples.
