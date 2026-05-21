# PR/FAQ

## Press Release

### Parallel Agents Office Launches a No-Code AI Software Company for Builders and Teams

Parallel Agents Office helps builders and software teams move from idea to release using coordinated AI agents that follow professional software company workflows.

Instead of asking users to know how to plan a product, choose a tech stack, write architecture documents, create issues, review code, run security checks, and prepare a release, Parallel Agents Office guides the work end to end. Users describe an idea or connect a repository, choose the outcome they want, and specialist agents run discovery, planning, architecture, implementation, testing, review, documentation, and release readiness in parallel.

Every run produces evidence: project briefs, PR/FAQ, architecture RFCs, tech stack decisions, issues, patches, risk reports, release notes, and measurable productivity data.

The first version focuses on GitHub-based software projects. Users can connect a repository, pick a workflow such as "review this project", "prepare a release", "fix failing tests", or "turn this idea into a roadmap", and receive structured outputs that can be reviewed and approved before changes are applied.

Parallel Agents Office is built on the open-source `parallel-agents` engine, which already supports specialist workers, evidence storage, MCP integration, PyPI/npm distribution, and evaluation tooling.

## Customer FAQ

### Who is this for?

Solo builders, small software teams, maintainers, and engineering leaders who want professional software workflows without manually coordinating every role.

### Is this just another coding agent?

No. A coding agent usually starts at implementation. Parallel Agents Office starts earlier: idea validation, project definition, stack choice, architecture, planning, implementation, review, release, and learning.

### Does it write code automatically?

Yes, but implementation is only one stage. The system can also produce plans, RFCs, test strategies, security reviews, docs, release checklists, and metrics.

### Can non-coders use it?

That is the target product direction. The engine remains available through CLI and MCP, but the public experience should be a no-code workflow where users choose project outcomes and approve changes.

### How is risk controlled?

The product uses permission profiles:

- `safe`: read-only analysis and planning.
- `team`: create branches, issues, draft PRs, and request approval for write actions.
- `owner`: apply approved patches in trusted repositories.
- `autonomous`: private/self-hosted mode for trusted operators only.

### What does a user get at the end?

Depending on the workflow:

- Product brief.
- PR/FAQ.
- Roadmap.
- Architecture RFC.
- Tech stack recommendation.
- GitHub issues.
- Pull request draft.
- Test and security report.
- Release notes.
- Rollback plan.
- Evaluation metrics.

## Internal FAQ

### Should we keep the current repo?

Yes. The current repo is a viable execution engine. It already has parallel workers, CLI, MCP server, evidence storage, tests, packaging, and evaluation support.

### Should we rename the package?

Not now. Keep `parallel-agents` for the engine. Use a separate product name for the no-code workspace.

### What is the first product milestone?

Add a professional operating layer: vision, PR/FAQ, quality bar, tech stack policy, operating model, roadmap, and workflows. Then implement structured project workflow objects in code.

### What is the smallest useful MVP?

A GitHub-first workflow that turns a project idea or issue into:

1. Product brief.
2. Tech stack recommendation.
3. Architecture RFC.
4. Roadmap and issues.
5. Parallel implementation or review run.
6. PR summary and release readiness report.

### What should not be built first?

Do not start with a full OpenClaw-style multi-channel personal assistant. That is too broad and not the strongest differentiation. Start with software-company workflows.

