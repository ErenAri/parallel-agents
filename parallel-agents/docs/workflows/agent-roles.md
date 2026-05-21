# Agent Roles

## Purpose

This document defines the specialist agents needed for a no-code AI software company workflow.

The current worker set already covers many implementation roles. Future work should add product, research, planning, release, and metrics roles.

## Existing Engine Roles

### Security Agent

Focus:

- Threat modeling.
- Vulnerability review.
- Secret and auth risk.
- Permission model review.

Outputs:

- Security findings.
- Severity.
- Mitigation steps.
- Release blockers.

### Test Agent

Focus:

- Unit/integration/e2e coverage.
- Regression risk.
- Test generation.
- CI failures.

Outputs:

- Test plan.
- Missing coverage.
- Suggested tests.
- Failure diagnosis.

### Performance Agent

Focus:

- Hot paths.
- Complexity.
- Resource usage.
- Scalability risk.

Outputs:

- Performance findings.
- Measurement suggestions.
- Optimization plan.

### DevOps Agent

Focus:

- CI/CD.
- Packaging.
- Release automation.
- Deployment readiness.

Outputs:

- Pipeline changes.
- Release risks.
- Build and deploy guidance.

### Architecture Agent

Focus:

- System design.
- Boundaries.
- Dependencies.
- Tradeoffs.

Outputs:

- RFC.
- Tech stack decision.
- Architecture risks.

### Docs Agent

Focus:

- README.
- User docs.
- Developer docs.
- Release notes.

Outputs:

- Documentation changes.
- Docs gaps.
- Onboarding improvements.

### Code Agent

Focus:

- Implementation.
- Refactoring.
- Bug fixes.

Outputs:

- Patches.
- PR summaries.
- Implementation notes.

### Review Agent

Focus:

- Code quality.
- Maintainability.
- Best practices.
- Regression risk.

Outputs:

- Review findings.
- Approval recommendation.
- Required changes.

## New Company Workflow Roles

### Product Agent

Focus:

- User problem.
- Product brief.
- PR/FAQ.
- Acceptance criteria.

Outputs:

- Product brief.
- PR/FAQ.
- Success metrics.

### Research Agent

Focus:

- Market and competitor research.
- Technical alternatives.
- User workflow evidence.

Outputs:

- Research memo.
- Source list.
- Risks and assumptions.

### Planning Agent

Focus:

- Roadmap.
- Epics.
- Issues.
- Sprint planning.
- Dependency mapping.

Outputs:

- Roadmap.
- Sprint plan.
- Issue list.
- Dependency map.

### Release Agent

Focus:

- Versioning.
- Changelog.
- Release readiness.
- Rollback plan.

Outputs:

- Release checklist.
- Release notes.
- Rollback plan.

### Metrics Agent

Focus:

- Productivity and effectiveness proof.
- Cost, token, time, quality metrics.
- Post-release learning.

Outputs:

- Scorecard.
- Evaluation report.
- Roadmap recommendations.

## Agent Coordination Rules

- Product and architecture agents decide what should be built before code starts.
- Code agents should not implement vague requirements.
- Security, test, and review agents should be able to block release.
- Release agent should not publish unless quality gates pass.
- Metrics agent should feed results back into planning.

