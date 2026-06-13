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
    memory/
```

## Initialize

```bash
parallel-agents office onboard --project . --name "Project Name"
parallel-agents office init --project . --name "Project Name"
parallel-agents office status --project .
parallel-agents office doctor --project .
parallel-agents office fix-setup --project .
parallel-agents office home --project .
parallel-agents office artifacts --project .
parallel-agents office artifacts --project . --run-id run-123
parallel-agents office memory add --project . --kind decision --title "Architecture call" --content "Use local gateway"
parallel-agents office memory list --project .
parallel-agents office memory search --project . --query "gateway"
parallel-agents office memory policies --project .
```

The standalone binary should support the same commands:

```bash
parallel-agents.exe office onboard --project .
parallel-agents.exe office init --project .
parallel-agents.exe office status --project .
parallel-agents.exe office doctor --project .
parallel-agents.exe office fix-setup --project .
parallel-agents.exe office home --project .
parallel-agents.exe office artifacts --project .
parallel-agents.exe office memory list --project .
```

## Product Shape

The desktop office should eventually provide:

- Command Center landing page for project state, readiness, recent runs, and fast actions
- top-level app chrome showing current project, gateway status, and LLM mode
- project selection rooted in a local folder
- first-run onboarding that prepares workspace setup and reports model/GitHub readiness
- immediate workspace-health diagnostics signal from `office doctor`
- one-click setup remediation path from desktop (`Fix Setup`) and CLI (`office fix-setup`)
- desktop-owned project gateway start/stop/status controls
- idea-to-release workflow controls
- run cockpit with state/worker/token/cost cards and event-native worker status
- approval queue before write actions, including bulk actions, artifact diff preview, and audit drilldown
- artifact browser for brief, roadmap, RFC, issue plan, release checks
- artifact-browser controls for search/filter/sort and quick open/export actions
- local metrics and audit history
- optional GitHub and MCP integrations (with explicit `gh` auth checks in desktop flow)
- local channel-adapter pairing/allowlist surface before real messaging connectors are enabled

## Non-Goals

- Mobile dashboard as the primary product surface
- Hosted web app as the first user experience
- Remote multi-tenant state before local workflow quality is stable

## Gateway Role

The gateway remains useful as an internal local job API and integration boundary. It should not define the user-facing product experience.

Use `POST /runs/pipeline` when a desktop shell, automation script, or MCP host needs the same persistent run/job/event lifecycle for a real planner/worker/judge pipeline run. The desktop can still present a local-first product surface while the gateway acts as the shared control plane behind it.

Desktop gateway behavior:

- `PA_DESKTOP_USE_GATEWAY=auto` probes `http://127.0.0.1:8733` and falls back to in-process runs if unavailable.
- `PA_DESKTOP_GATEWAY_URL=http://host:port` points the desktop at a specific gateway.
- `PA_DESKTOP_GATEWAY_REQUIRED=1` fails fast when the gateway cannot be reached.
- `PA_DESKTOP_GATEWAY_HOST`, `PA_DESKTOP_GATEWAY_PORT`, and `PA_DESKTOP_GATEWAY_START_TIMEOUT` tune the desktop-owned gateway process.
- Generated patches create a pending `final-output` approval; desktop PR creation requires approval of the current artifact digest.

The desktop-owned gateway is a session process, not an OS daemon. Closing the desktop stops owning the process; production installer work should add tray/daemon lifecycle and auto-restart.

## Channel Adapter Role

The gateway now exposes a local channel-adapter boundary for future messaging connectors. Unknown inbound senders receive a pairing code and are not processed until approved. This matches the required security posture for real DM/chat channels, but it is not a full Slack/Discord/Telegram connector yet.
