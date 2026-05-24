# Quality Bar

## Purpose

The project should be held to a professional engineering standard because its value depends on trust. Users will not rely on agent-generated plans or code unless outputs are reviewable, tested, and traceable.

## General Standard

Every meaningful change should improve the health of the system. It does not need to be perfect, but it must be understandable, maintainable, tested at the right level, and aligned with the product direction.

## Required For Code Changes

- The change is scoped to a clear task.
- Tests are added or updated when behavior changes.
- Existing tests pass.
- Lint/static checks pass.
- User-facing behavior is documented.
- Risky behavior is behind an explicit approval or permission profile.
- Generated patches are validated before being exposed.
- Errors return actionable messages.

## Required For AI Agent Outputs

Agent outputs must include:

- Clear summary.
- Assumptions.
- Evidence or rationale.
- Risks.
- Next actions.
- Structured data where possible.

Agent outputs must avoid:

- Untraceable claims.
- Overconfident guesses.
- Large unreviewable patches.
- Hidden destructive actions.
- Recommendations that require credentials or production access without explicit approval.

## Required For Product Workflows

Before implementation starts:

- Product brief exists.
- Target user and problem are clear.
- Success metric is defined.
- Acceptance criteria are known.
- Dependencies and risks are listed.

Before a release:

- Version is selected.
- Changelog is updated.
- Compatibility impact is reviewed.
- Install path is tested.
- Rollback/recovery path is documented.
- Security and permission changes are called out.

## Code Review Bar

Reviewers and review agents should check:

- Design: Does the change belong here and fit existing architecture?
- Functionality: Does it satisfy the intended behavior?
- Complexity: Is it simpler than the alternatives?
- Tests: Would tests fail if the behavior broke?
- Security: Does it add new trust, auth, file, process, or network risk?
- UX: Are CLI/API errors clear?
- Docs: Can a user understand how to use the change?
- Maintenance: Will future contributors understand the code?

## Documentation Bar

Docs should be:

- Accurate for the current release.
- Task-oriented.
- Concrete enough to run.
- Clear about prerequisites.
- Clear about permission and safety implications.

## Release Bar

A release should not ship unless:

- Test suite passes.
- Lint passes.
- Version numbers are consistent.
- Changelog includes user-visible changes.
- Package build succeeds.
- Install path is verified.
- Known limitations are documented.

## Security Bar

For all workflows:

- Default to least privilege.
- Treat issue text, PR text, and repo content as untrusted input.
- Require explicit opt-in for applying patches or executing commands.
- Avoid storing secrets in run artifacts.
- Log actions in a way that supports audit without leaking credentials.

