# Tech Stack Policy

## Purpose

This project should avoid random tool choices. A professional product needs a small, stable stack that contributors can understand, test, secure, and release.

## Current Approved Stack

### Engine

- Python 3.11+
- Pydantic / pydantic-settings
- Click
- Rich
- pytest
- ruff

### Agent Runtime

- Claude Code SDK path where available.
- Claude CLI fallback path.
- MCP server support through the official MCP Python package.

### Storage

- File evidence store for local/default usage.
- SQLite evidence store for structured local history.

### Packaging

- PyPI package via Hatchling.
- npm wrapper for `npx` usage.
- Standalone binary through PyInstaller.

## Future Approved Stack Candidates

These are candidates, not commitments.

### No-Code Web Product

- Backend: Python FastAPI or Node/TypeScript.
- Frontend: Next.js or Vite React.
- Database: Postgres for hosted product, SQLite for local desktop/self-host mode.
- Queue: Redis/RQ, Celery, or durable cloud queue depending on deployment target.
- Auth: OAuth for GitHub and MCP connectors.

### Hosted MCP

- Remote MCP over HTTP/SSE or streamable HTTP as supported by clients.
- OAuth where public connectors require user identity.
- Per-workspace rate limits and audit logs.

### Deployment

- GitHub Actions for CI.
- PyPI/npm provenance where available.
- Container image for hosted/gateway deployments.

## Default Decision Rule

Use the current approved stack unless a new requirement cannot be solved cleanly with it.

Adding a new framework, database, queue, or hosting dependency requires a documented decision.

## Tech Stack Decision Template

For nontrivial technology decisions, create a `TechStackDecision` with:

- Problem.
- Options considered.
- Recommendation.
- Decision owner.
- Success criteria.
- Security impact.
- Operational impact.
- Cost impact.
- Migration/rollback plan.

## Scoring Rubric

Score each option from 1 to 5:

- Product fit.
- Delivery speed.
- Maintainability.
- Team familiarity.
- Ecosystem maturity.
- Security posture.
- Testability.
- Observability.
- Packaging/deployment simplicity.
- Cost.

Prefer the highest total score unless a critical constraint overrides it.

## Exception Policy

Exceptions are allowed when justified, but must be explicit.

Use an RFC or decision document when:

- Introducing a new runtime.
- Introducing a persistent service.
- Changing package or release mechanics.
- Adding production write actions.
- Changing authentication or permission behavior.
- Creating a hosted component.

