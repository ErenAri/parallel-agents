# Idea To Release Workflow

## Purpose

This workflow describes how the product should turn a rough project idea into a release-ready software change using AI agents and professional software company practices.

## Stage 1: Idea Intake

Input:

- Plain-language idea.
- Optional repository.
- Optional business/user context.

Output:

- Product brief.
- Assumptions.
- Unknowns.
- Initial success metric.

Agent owner:

- Product Agent.

Gate:

- User approves that the problem is worth exploring.

## Stage 2: Research

Input:

- Product brief.
- Target user.
- Competitors or comparable workflows.

Output:

- Research summary.
- Evidence.
- Risks.
- Open questions.

Agent owner:

- Research Agent.

Gate:

- Enough evidence exists to write a PR/FAQ or the idea is rejected.

## Stage 3: PR/FAQ

Input:

- Product brief.
- Research summary.

Output:

- Future press release.
- Customer FAQ.
- Internal FAQ.
- Success criteria.

Agent owner:

- Product Agent.

Gate:

- User decides: start, revise, or stop.

## Stage 4: Tech Stack Decision

Input:

- PR/FAQ.
- Existing repo constraints.
- Security, cost, and deployment needs.

Output:

- Options.
- Scorecard.
- Recommended stack.
- Exception notes if deviating from approved stack.

Agent owner:

- Architecture Agent.

Gate:

- User approves stack decision.

## Stage 5: Architecture RFC

Input:

- Approved product direction.
- Approved stack.

Output:

- System design.
- Data model.
- APIs/commands.
- Security model.
- Failure modes.
- Rollout plan.
- Alternatives considered.

Agent owner:

- Architecture Agent.

Gate:

- RFC passes review.

## Stage 6: Roadmap And Issues

Input:

- PR/FAQ.
- Architecture RFC.

Output:

- Epics.
- Issues.
- Milestones.
- Dependencies.
- Acceptance criteria.

Agent owner:

- Planning Agent.

Gate:

- Sprint scope selected.

## Stage 7: Implementation

Input:

- Sprint plan.
- Issues.
- Acceptance criteria.

Output:

- Branches.
- Code changes.
- Tests.
- Docs.
- Draft PRs.

Agent owners:

- Code Agent.
- Test Agent.
- Docs Agent.
- DevOps Agent.

Gate:

- CI and local checks pass.

## Stage 8: Review

Input:

- Pull request or patch.
- Test results.
- Risk report.

Output:

- Review findings.
- Required changes.
- Approval recommendation.

Agent owners:

- Review Agent.
- Security Agent.

Gate:

- Quality bar passes.

## Stage 9: Release Readiness

Input:

- Merged or release-candidate changes.
- Changelog.
- Version.
- Test results.

Output:

- Release readiness report.
- Rollback plan.
- Known issues.
- Release notes.

Agent owner:

- Release Agent.

Gate:

- User approves release.

## Stage 10: Release

Input:

- Approved release readiness report.

Output:

- Published package or deployment.
- Git tag.
- Release notes.
- Post-release monitoring checklist.

Agent owners:

- Release Agent.
- DevOps Agent.

Gate:

- Smoke checks pass.

## Stage 11: Post-Release Learning

Input:

- Metrics.
- User feedback.
- Incidents.
- Support questions.

Output:

- Post-release review.
- Follow-up issues.
- Roadmap update.

Agent owner:

- Metrics Agent.

