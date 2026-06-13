# Gateway API Workflow

## Purpose

This document describes how to use the local gateway as an internal durable backend for project-office automation and agent-driven workflow surfaces.

The gateway stores project/run/job/event state in SQLite at:

- `.parallel-agents/gateway.sqlite`

and stores artifact payloads under:

- `.parallel-agents/<run-id>/company/*.json`

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
- `GET /metrics/summary`

### Projects

- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`

### Workspace Memory

- `POST /memory/entries`
- `GET /memory/entries`
- `GET /memory/search`
- `GET /memory/policies`
- `PUT /memory/policies`

### Channel Adapter

- `POST /channels/slack/events`
- `POST /channels/inbound`
- `POST /channels/pairing/approve`
- `GET /channels/peers`

`POST /channels/inbound` is the local adapter boundary for future Slack/Discord/Telegram-style connectors. Unknown senders are not processed. They receive a short pairing code:

```json
{
  "channel": "slack",
  "peer_id": "U123",
  "message": "Review this repository",
  "execute": true
}
```

Unknown sender response:

```json
{
  "status": "pairing_required",
  "processed": false,
  "pairing_code": "A1B2C3"
}
```

Approve locally:

```json
{
  "code": "A1B2C3",
  "approved_by": "operator"
}
```

After approval, `execute=true` can enqueue a `pipeline.run`; if `execute` is omitted or false, the message is accepted but not processed.

### Slack Events

`POST /channels/slack/events` is the first real channel connector boundary. Configure Slack Event Subscriptions to point at this endpoint through a public HTTPS tunnel or deployment. The endpoint:

- verifies `X-Slack-Signature` using `PA_GATEWAY_SLACK_SIGNING_SECRET` / `--slack-signing-secret`
- responds to Slack `url_verification` with the challenge value
- ignores bot/subtype messages
- maps message events to the local `slack` channel adapter
- still requires local pairing before a Slack sender can enqueue work

For local tunnel testing only, `PA_GATEWAY_SLACK_ALLOW_UNSIGNED=1` or `--allow-unsigned-slack` skips signature verification. Do not use unsigned mode for an exposed gateway.

Recommended Slack setup:

```bash
set PA_GATEWAY_SLACK_SIGNING_SECRET=<slack-signing-secret>
parallel-agents gateway start --host 127.0.0.1 --port 8733
```

Then expose `http://127.0.0.1:8733/channels/slack/events` through a trusted HTTPS tunnel and configure that public URL in Slack Event Subscriptions. Subscribe only to the message events needed for the first workflow, and keep the gateway bound to localhost unless the deployment has API key/JWT protection and Slack signature verification enabled.

Connector priority:

- Slack is the first real connector because it best matches software-company workflows.
- Telegram is the next recommended connector for personal-assistant usage.
- Discord should follow after Slack/Telegram because community-server routing and bot/subtype handling need more product decisions.

CLI equivalents:

```bash
parallel-agents gateway channel inbound \
  --channel slack \
  --peer-id U123 \
  --message "Review this repository" \
  --execute

parallel-agents gateway channel approve --code A1B2C3 --approved-by operator
parallel-agents gateway channel peers --channel slack
```

### Company Workflows

- `POST /runs/company/idea`
- `POST /runs/company/roadmap`
- `POST /runs/company/plan`
- `POST /runs/company/approve`
- `POST /runs/company/apply`

### Pipeline Runs

- `POST /runs/pipeline`

`POST /runs/pipeline` executes the core planner/worker/judge pipeline through the same local job system used by company workflows. Required payload:

```json
{
  "run_id": "run-123",
  "task": "Review this repository and propose a safe PR",
  "repo_path": "./my-project"
}
```

Optional payload fields mirror the CLI: `workers`, `disable_workers`, `model`, `permission_mode`, `store_backend`, `max_parallel_workers`, `parse_retry_attempts`, `wait`, and `wait_timeout_seconds`.

Pipeline status messages are appended to `GET /runs/{run_id}/events` as `pipeline_status`. Structured trace events are appended as `pipeline_trace` with payload fields such as `agent`, `phase`, `status`, `event`, `batch`, and `workers`. The final output is available as artifact `final-output`.

The desktop office can submit runs through this endpoint when `PA_DESKTOP_USE_GATEWAY` is enabled, a gateway is detected locally, or the desktop starts its project-scoped gateway process. When a generated patch is present in `final-output`, the desktop creates a review approval and blocks PR creation until that exact artifact digest is approved.

### Run Inspection and Control

- `GET /runs`
- `GET /runs/{run_id}`
- `POST /runs/{run_id}/cancel`
- `POST /runs/{run_id}/retry`
- `GET /runs/{run_id}/jobs`
- `GET /runs/{run_id}/artifacts/{artifact_name}`
- `GET /runs/{run_id}/artifacts`
- `GET /runs/{run_id}/events`

## Request Patterns

Most run-creation endpoints accept:

- `wait` (default `true`): return when run reaches a terminal status.
- `wait_timeout_seconds` (default `30`): polling timeout for synchronous responses.

For queue-style behavior from a desktop shell, CLI wrapper, or external orchestrator:

- send `wait=false`
- poll `GET /runs/{run_id}`
- read events from `GET /runs/{run_id}/events`

## Safety Model

- `company plan -> approve -> apply` keeps write actions approval-gated.
- `company apply` enforces policy checks before any GitHub write attempt.
- Approval changes produce immutable audit log entries.
