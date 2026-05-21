# Local Desktop Office Workflow

## Purpose

Parallel Agents Office is moving toward a local `.exe` experience that works inside a project folder. The project folder is the source of truth, not a hosted web dashboard.

## Workspace Layout

```text
project/
  .parallel-agents/
    project.json
    runs/
    artifacts/
    approvals/
    audit/
    metrics/
```

## Initialize

```bash
parallel-agents office init --project . --name "Project Name"
parallel-agents office status --project .
parallel-agents office home --project .
parallel-agents office artifacts --project .
parallel-agents office artifacts --project . --run-id run-123
```

The standalone binary should support the same commands:

```bash
parallel-agents.exe office init --project .
parallel-agents.exe office status --project .
parallel-agents.exe office home --project .
parallel-agents.exe office artifacts --project .
```

## Product Shape

The desktop office should eventually provide:

- project selection rooted in a local folder
- idea-to-release workflow controls
- run queue and worker status
- approval queue before write actions
- artifact browser for brief, roadmap, RFC, issue plan, release checks
- local metrics and audit history
- optional GitHub and MCP integrations

## Non-Goals

- Mobile dashboard as the primary product surface
- Hosted web app as the first user experience
- Remote multi-tenant state before local workflow quality is stable

## Gateway Role

The gateway remains useful as an internal local job API and integration boundary. It should not define the user-facing product experience.
