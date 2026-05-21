# Operating Model

## Purpose

This document defines how `parallel-agents` should operate like a small professional software company powered by AI agents.

The goal is to make the system repeatable, inspectable, and safe enough to produce high-quality software work.

## Workflow Overview

```text
Idea
  -> Product Brief
  -> Research and PR/FAQ
  -> Decision to Start
  -> Tech Stack Decision
  -> Architecture RFC
  -> Roadmap and Issues
  -> Sprint Plan
  -> Parallel Implementation
  -> Review and Quality Gates
  -> Release Readiness
  -> Release
  -> Post-Release Learning
```

## Planning Cadence

The product should use a lightweight version of large-company planning:

- **Strategy**: 12-month product direction.
- **Season**: 6-month major outcome.
- **Plan**: 3-sprint execution window.
- **Sprint**: 2-3 week implementation cycle.
- **Daily/Run**: individual agent jobs and reviews.

For this repo, keep the cadence pragmatic:

- Roadmap reviewed monthly.
- Sprint scope reviewed weekly while the product is early.
- Release readiness checked before every public package release.

## Project Roles

AI agents should map to recognizable software-company roles:

- **Product Agent**: Defines user, problem, outcome, PR/FAQ, acceptance criteria.
- **Research Agent**: Looks up market, user, technical, and competitor evidence.
- **Architecture Agent**: Produces RFCs, stack decisions, diagrams, tradeoffs.
- **Planning Agent**: Breaks work into epics, issues, dependencies, milestones.
- **Code Agent**: Implements scoped code changes.
- **Test Agent**: Adds tests and identifies regression risk.
- **Security Agent**: Threat models, scans, and reviews risky behavior.
- **DevOps Agent**: CI/CD, packaging, deployment, release automation.
- **Docs Agent**: Maintains user docs, developer docs, release notes.
- **Review Agent**: Reviews changes against the quality bar.
- **Release Agent**: Prepares release checklist, versioning, changelog, rollback plan.
- **Metrics Agent**: Measures productivity, quality, cost, and effectiveness.

## Decision Model

Use a DACI-style model for nontrivial decisions:

- **Driver**: Agent or user responsible for collecting context and pushing the decision forward.
- **Approver**: Human or policy gate that makes the final call.
- **Contributors**: Agents or people that provide evidence.
- **Informed**: Stakeholders notified after the decision.

For solo usage, the user is usually the Approver.

## Decision Artifacts

Every substantial project should produce:

- `ProductBrief`
- `PRFAQ`
- `TechStackDecision`
- `ArchitectureRFC`
- `Roadmap`
- `SprintPlan`
- `ReleaseReadinessReport`
- `PostReleaseReview`

These should eventually be first-class models in the codebase, not only Markdown documents.

## Permission Profiles

### safe

Read-only mode. Default for public no-code usage.

Allowed:

- Repository analysis.
- Planning.
- Reports.
- Suggested patches.

Denied:

- Applying patches.
- Creating branches.
- Opening PRs.
- Running destructive commands.

### team

Collaboration mode for connected repositories.

Allowed:

- Create issues.
- Create branches.
- Open draft PRs.
- Run CI.

Requires approval:

- Merge PR.
- Release package.
- Deploy production changes.

### owner

Trusted owner mode.

Allowed:

- Apply approved patches.
- Create releases.
- Update package metadata.

Requires approval:

- Destructive file operations.
- Credential changes.
- Production deploys.

### autonomous

Private/self-hosted mode only.

Allowed:

- Run with minimal prompts.

Required safeguards:

- Audit log.
- Rollback plan.
- Workspace boundaries.
- Explicit opt-in.

## Quality Gates

Before merge or release:

- Product goal is clear.
- Tech stack decision is documented if new tools are introduced.
- Architecture RFC exists for nontrivial design changes.
- Tests pass.
- Lint/static checks pass.
- Security risks are reviewed.
- Docs are updated.
- Release notes are prepared.
- Rollback path is known.

## Metrics

Track product and engineering outcomes:

- Time from idea to first useful artifact.
- Time from issue to PR.
- PR acceptance rate.
- Reviewer minutes saved.
- Regression rate.
- Finding precision.
- Test pass rate.
- Cost per run.
- User activation rate.
- Release frequency.
- Mean time to recover from failed release.

