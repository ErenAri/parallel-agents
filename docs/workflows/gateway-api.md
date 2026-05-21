# Gateway API Workflow

## Purpose

This document describes how to use the local gateway as a durable backend for no-code and agent-driven workflow surfaces.

The gateway stores project/run/job/event state in SQLite at:

- `.parallel-agents-output/gateway.sqlite`

and stores artifact payloads under:

- `.parallel-agents-output/<run-id>/company/*.json`

## Start Gateway

```bash
parallel-agents gateway start --host 127.0.0.1 --port 8733
```

Optional API key protection:

```bash
set PA_GATEWAY_API_KEY=my-secret
parallel-agents gateway start --host 0.0.0.0 --port 8733
```

or:

```bash
parallel-agents gateway start --api-key my-secret
```

## Authentication

When API key protection is enabled, all endpoints except `GET /health` require one of:

- `X-PA-API-Key: <key>`
- `Authorization: Bearer <key>`

## Run Execution Model

- Runs are persisted as `queued`, then processed by an in-process worker.
- Statuses:
  - `queued`
  - `running`
  - `waiting_for_approval`
  - `blocked_by_policy`
  - `succeeded`
  - `failed`
- `POST /runs/{run_id}/cancel` requests cancellation.
- `POST /runs/{run_id}/retry` requeues retryable runs.
- Run events are appended for enqueue/start/status/complete/cancel lifecycle steps.

## Endpoints

### Health

- `GET /health`

### Projects

- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`

### Company Workflows

- `POST /runs/company/idea`
- `POST /runs/company/roadmap`
- `POST /runs/company/plan`
- `POST /runs/company/approve`
- `POST /runs/company/apply`

### Run Inspection and Control

- `GET /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/cancel`
- `POST /runs/{run_id}/retry`
- `GET /runs/{run_id}/jobs`
- `GET /runs/{run_id}/artifacts`
- `GET /runs/{run_id}/events`

## Request Patterns

Most run-creation endpoints accept:

- `wait` (default `true`): return when run reaches a terminal status.
- `wait_timeout_seconds` (default `30`): polling timeout for synchronous responses.

For queue-style behavior from a UI or external orchestrator:

- send `wait=false`
- poll `GET /runs/{run_id}`
- read events from `GET /runs/{run_id}/events`

## Safety Model

- `company plan -> approve -> apply` keeps write actions approval-gated.
- `company apply` enforces policy checks before any GitHub write attempt.
- Approval changes produce immutable audit log entries.
