# Vision

## Product Thesis

`parallel-agents` should become the execution engine for **Parallel Agents Office** — a no-code **AI software company OS**.

The public product should feel less like a coding script and more like a small professional software company: a user brings a project idea, and the system runs discovery, planning, architecture, implementation, review, release, and post-release learning through coordinated AI agents.

Framed after Andrej Karpathy's "org code" thesis, an agent organization is a *topology + rules* for how nodes communicate, decide, and escalate — declarable as code you can **fork, diff, and mutate**, and made fully **legible** so a human conductor can watch and steer it live, from the whole-org graph down to one agent's token stream.

## Product Name

Working product name: **Parallel Agents Office**

Package and engine name: **parallel-agents**

This keeps the current package useful for developers while giving the larger product a clearer identity for non-coders and teams.

## Target Users

### Solo Builder

Wants to turn ideas into working software without managing every engineering step manually.

Needs:

- Clear project plan from a rough idea.
- Suggested tech stack and tradeoffs.
- Working pull requests instead of vague advice.
- Low setup burden.

### Small Software Team

Wants faster planning, review, testing, and release without hiring a full specialist team.

Needs:

- Repeatable workflows.
- Evidence-backed decisions.
- Reviewable changes.
- Security, test, docs, and release gates.

### Engineering Leader

Wants productivity gains without losing quality, traceability, or governance.

Needs:

- Metrics.
- Audit trails.
- Risk controls.
- Clear ownership and approval gates.

## Product Promise

Given a project idea or repository, Parallel Agents Office can:

1. Understand the product goal.
2. Research the problem and alternatives.
3. Produce product and technical planning artifacts.
4. Break the work into an executable roadmap.
5. Run specialist agents in parallel.
6. Generate evidence-backed patches, pull requests, reports, and release notes.
7. Measure productivity, quality, and release risk.

## Operating Principles

- **Outcome before output**: The system must optimize for useful shipped work, not agent activity.
- **Evidence over confidence**: Agent recommendations must include traceable evidence, tradeoffs, or assumptions.
- **Small reviewable changes**: Large changes must be decomposed into small PR-sized units.
- **Human-controlled risk**: Public and team usage should require approval for destructive or production-impacting actions.
- **Standard stack by default**: The system should prefer approved, well-understood tools unless an RFC justifies an exception.
- **Release from day one**: Build, test, packaging, docs, monitoring, and rollback planning are part of product work, not cleanup.

## Non-Goals

- Do not become a general personal assistant like OpenClaw.
- Do not default public users into unrestricted machine control.
- Do not optimize for demo-only code that cannot be tested, released, or maintained.
- Do not create a new framework when a standard tool or existing repo pattern is sufficient.

## Strategic Direction

The near-term project should remain a Python engine with CLI and MCP integration.

The next product layer should add:

- Company workflow artifacts.
- Project/session state.
- Idea-to-release orchestration.
- Remote MCP API surface.
- Local desktop/project-folder office.
- GitHub-first delivery.
- Evaluation metrics that prove productivity and effectiveness.
