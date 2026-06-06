# Org-Code: Deep Research

*Building an "agent command center" where parallel AI agents work like a company — orchestrated by declarable, forkable org structures, with full real-time legibility.*

Prepared for Eren · June 2026

---

## 1. The thesis, stated plainly

Andrej Karpathy's two posts contain one idea split across two timescales.

The near-term half (his reply to Numman Ali) is a tooling complaint: people already run teams of coding agents in tmux grids, but tmux is a dumb window manager. He wants a "proper agent command center IDE" — maximize per monitor, show/hide each agent, see at a glance which are idle, pop open their tools and usage stats.

The deeper half (his "org code" post) is a claim about what an organization *is*. Amazon, Google, Facebook, Microsoft, Apple, and Oracle are drawn as different graph topologies — a clean tree, a dense mesh, a star, isolated clusters. The insight: an org is just a **topology plus a set of rules for how nodes communicate, decide, and escalate**, and that is a program. You can't fork Microsoft, but if the org is code, you can instantiate it, clone it, diff it, and mutate it. His second post adds the missing ingredient — **legibility**: human orgs are illegible (a CEO can't zoom into live activity), but an agentic org could be fully inspectable, top to bottom.

These are not two projects. The command center is the **legibility plane** of the org-code system. Build the legibility/observability layer first; the forkable-org layer is what that plane lets you see and edit. This document maps what already exists, what the idea actually requires, and where the genuine white space is.

---

## 2. Prior art: "agents as a company"

Two well-known systems already implement the literal "agents run a company" premise, and both are instructive precisely because of where they stop.

**MetaGPT** encodes the thesis in a formula: `Code = SOP(Team)`. It argues software quality comes not from individual brilliance but from **Standard Operating Procedures** executed by specialized roles. It assigns five fixed roles — Product Manager, Architect, Project Manager, Engineer, QA Engineer — and passes work down an assembly line: a one-line requirement becomes a PRD, then a design, then tasks, then code, then tests, via structured handoffs that mimic decades-old software workflows.

**ChatDev** models a "virtual software company" running the **waterfall** lifecycle in four phases (Design → Code → Test → Document). Its coordination primitive is the **chat chain**: each phase is split into small two-agent dialogues (e.g. CTO instructs programmer), with a "communicative dehallucination" technique to reduce errors. Roles include CEO, CTO, programmer, reviewer, tester, and designer.

The lesson from both: they prove role-specialization plus a defined procedure produces better output than one monolithic agent — but the **org is hardcoded**. The topology is a fixed pipeline baked into the framework. You cannot change the shape, you cannot fork it, you cannot watch it run in real time, and you cannot A/B one org design against another. They are batch tools that emit a repo, not living, observable, editable organizations. That fixed-ness is exactly the constraint "org code" is meant to dissolve.

---

## 3. Prior art: orchestration frameworks (the plumbing)

The general-purpose multi-agent frameworks each commit to one coordination *shape*, which is revealing — it confirms that topology is the core design variable.

| Framework | Coordination model | Native topology | Notable for |
|---|---|---|---|
| **LangGraph** | Directed graph with conditional edges; built-in checkpointing + "time travel" | Arbitrary graph | Most production-ready for stateful, observable agents |
| **CrewAI** | Role-playing "crew": each agent has role, goal, backstory; process types | Role hierarchy / sequential | Lowest barrier — a crew in ~20 lines; fast prototyping |
| **AutoGen** (Microsoft) | Conversational `GroupChat`; a selector picks who speaks next | Multi-party conversation / mesh | Debate, consensus, the most diverse conversation patterns |
| **OpenAI Agents SDK** | Agents + Tools + **Handoffs** + Guardrails; triage agent routes to specialists | Handoff chain / star | Production successor to Swarm; OpenTelemetry tracing built in |
| **Anthropic Research** | **Orchestrator-worker**: lead plans, spawns parallel subagents | Star (lead + workers) | The reference design for parallel research (see §4) |

The takeaway: every framework *is* a topology with a runtime. None of them treats topology as a first-class, swappable, forkable artifact that you author separately from the agents — they bake one shape in. That's the gap "org code" targets: making the shape itself the editable object.

---

## 4. The reference design: Anthropic's orchestrator-worker system

Anthropic's published account of its Research system is the most rigorous public data point, and it directly substantiates several claims the org-code project rests on.

Architecture is an **orchestrator-worker** pattern: a lead agent (Claude Opus 4) analyzes the query, writes a plan, saves it to memory so it survives context truncation, then spawns parallel subagents (Claude Sonnet 4), each with its own context window, its own tools, and a clearly bounded task. Subagents act as parallel "compression" engines — each explores one slice and returns only the distilled tokens. A final CitationAgent attributes claims to sources.

The hard numbers matter for the project's economics:

- The multi-agent system **outperformed single-agent Opus 4 by 90.2%** on Anthropic's internal research eval.
- **Token usage alone explains ~80% of performance variance** (tool calls and model choice are the other factors). Multi-agent systems work largely *because* they spend more tokens against a problem.
- Cost is real: agents use **~4× the tokens of chat**, and **multi-agent systems ~15× chat tokens**. The economics only close on high-value tasks.
- Coordination is genuinely hard: early versions spawned 50 subagents for trivial queries, duplicated each other's work, and "distracted each other with excessive updates." Their fix was prompt-level scaling rules and explicit division of labor — i.e. *org rules*.
- They flag that **coding is a weaker fit than research** today: fewer truly parallelizable subtasks, and "LLM agents are not yet great at coordinating and delegating to other agents in real time."

Two engineering lessons transfer straight into the plan. First, **synchronous execution is a bottleneck** — their lead waits for each batch of subagents, so the lead can't steer mid-flight and one slow worker blocks everyone; async is the next frontier but adds state-consistency pain. Second, **route large outputs through a filesystem, not through the lead's context**, to avoid the "game of telephone" where information degrades each time it passes through the orchestrator. That is the concrete, measured version of the "lossy escalation" problem.

---

## 5. The substrate already exists: Claude Code Agent Teams

The single most important finding for feasibility: Anthropic shipped (experimentally) most of the coordination primitives the command center would need. **Claude Code Agent Teams** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, v2.1.32+) provides:

- **A team lead + independent teammates**, each a full Claude Code session with its own context window.
- **A shared task list** with three states (pending / in progress / completed) and **dependency tracking** — blocked tasks auto-unblock when their dependency completes. Task claiming uses **file locking** to avoid races.
- **A mailbox** for direct peer-to-peer messaging between teammates (not just report-up-to-lead, which is the subagent limitation).
- **Idle notifications**: when a teammate finishes and stops, it automatically notifies the lead.
- **Lifecycle hooks** — `TeammateIdle`, `TaskCreated`, `TaskCompleted` — that fire on exactly the events a dashboard needs, and can block/redirect work (exit code 2 sends feedback and keeps a teammate working).
- **Local, readable state on disk**: team config at `~/.claude/teams/{team}/config.json` (includes a `members` array, session IDs, pane IDs) and the task list under `~/.claude/tasks/{team}/`.

This is decisive. The "command center" does not have to invent agent orchestration from scratch — it can **read that on-disk state and subscribe to those hooks** to get a live, accurate picture of every agent's status, tasks, and messages. Idle detection — the killer feature, the thing tmux can't do — is a *first-class event* (`TeammateIdle` + idle notifications), not something you have to scrape from terminal output.

But the substrate's **limitations are equally important**, because they define the project's hard boundary:

- **The lead is fixed** for the team's lifetime; you can't promote or transfer leadership.
- **No nested teams** — teammates cannot spawn their own teammates. Every team is therefore **one level deep: a star** (lead + flat set of workers).
- **One team at a time** per lead.
- **In-process teammates don't survive `/resume` or `/rewind`.**
- **Split-pane mode needs tmux or iTerm2** and is *not supported in VS Code's integrated terminal, Windows Terminal, or Ghostty*; only in-process mode works everywhere.

The structural consequence is the crux of the whole project: **natively, Agent Teams can only express a star.** Real "org code" — trees, meshes, clustered divisions — cannot be built by configuring Agent Teams alone. Either you live inside the star for v1, or you build a layer that orchestrates *multiple* Claude Code processes (each the lead of its own star) wired together through files and messaging to compose deeper topologies. That choice is the central architectural fork of the plan (§ plan doc).

Note for this machine specifically: you're on **Windows**, where split-pane tmux mode is unsupported. That actually *strengthens* the case for a custom GUI command center over the tmux-grid approach Karpathy is reacting to — the tmux path is effectively macOS/Linux-only, so a cross-platform GUI fills a real gap rather than re-skinning an existing one.

---

## 6. Competitive landscape: the command center, today

A cluster of tools already productizes "run many coding agents at once." Studying them shows the market has converged on one pattern — and left the interesting half untouched.

- **Conductor** (Melty Labs, ~$22M Series A) — a Mac app whose whole premise is running many agents at once; a GUI wrapper that spawns one agent per task in its own **git worktree** so you stop hand-managing branches.
- **Vibe Kanban** — an open-source **kanban board** for agents: task cards with prompts, drag to "In Progress," each card gets a worktree + branch, review diffs in-board. (Its company, Bloop, shut down in early 2026; continues as community OSS.)
- **Claude Squad** — coordinates Claude Code / Codex / Aider via **tmux + git worktrees** for isolation; session management and change review.
- **Crystal** — an **Electron** desktop app running multiple Claude Code sessions in parallel worktrees with conversation tracking and diff visualization.
- **Nimbalyst** — a visual workspace combining kanban with mockups, diagrams, multi-editor workflows.

Every one of these is the same shape: **flat parallelism + git-worktree isolation + a kanban/diff review surface.** They are "the tmux grid, productized" — which is genuinely useful, but it is exactly the thing Karpathy says is good-and-not-enough. None of them models an **organization** (roles, topology, escalation rules), none lets you **fork an org design**, and none offers deep **legibility** (zoom from a whole-org graph down to one agent's live token stream). They manage *windows*; they do not manage an *org*.

On the pure observability side, **LangSmith** (token/latency/cost dashboards, P50/P99), **AgentOps** (session-lifecycle tracking, per-agent cost attribution, replay of multi-agent runs), **Langfuse** (self-hosted), and **Arize Phoenix** exist — but they are framework-level tracing for production telemetry, not an interactive control surface for a human steering a live team. They tell you what *happened*; the command center is about what's *happening* and what to do about it now.

---

## 7. The org-as-code thesis, examined

With the landscape mapped, here is why the idea is intellectually real and not just a UI wish.

**Topology is the coordination strategy, and different tasks want different shapes.** The org diagrams aren't decorative — each encodes a classic distributed-systems tradeoff:

| Shape | Example | Strength | Cost / failure mode | Best-fit work |
|---|---|---|---|---|
| **Tree** | Amazon | Cheap coordination (O(log n) depth), clean decomposition | Lossy escalation; a bad parent poisons its subtree | Decomposable build tasks |
| **Star** | Apple / orchestrator-worker | Total coherence and taste at the hub | Hub is bottleneck + single point of failure | Vision/coherence-critical work |
| **Mesh** | Google / Facebook | Rich context-sharing, robust | O(n²) communication; can thrash | Research where everyone needs everyone's findings |
| **Clusters** | Microsoft | Modular, isolated failure domains | Silos, cross-cluster gaps | Independent parallel workstreams |
| **Deep hierarchy + sidecars** | Oracle | Strong control, specialized functions | Slow, lossy | Compliance-heavy, top-down work |

So the real job of an org-code IDE is to make topology a **tunable knob** and ideally learn which shape fits which task.

**Communication is priced in tokens** — a constraint human orgs don't feel as sharply. Every inter-agent message is money, latency, and context-window pressure; a mesh of 8 agents is quadratic token burn. Anthropic's 15× figure is this made concrete. Org design therefore becomes a real optimization under a budget, not a matter of taste.

**Bounded context is the agent version of bounded rationality** — and it explains *why hierarchy exists at all*. A human manager's span of control is limited by attention; an agent-manager's is limited by its context window. Hierarchy isn't tradition; it's a forced consequence of finite context. This predicts that as context windows grow, optimal org depth shrinks.

**Conway's Law becomes a controllable lever.** Systems mirror the communication structure that builds them — and in an agent org you *set* that structure by fiat, instantly. The "inverse Conway maneuver" (design the org to produce the architecture you want) goes from a multi-quarter reorg to a config change.

**Lossy escalation survives even with total legibility** — and Anthropic measured it (the "game of telephone"). A sub-agent summarizing up to its manager loses information by definition. So the human overseer can zoom to any agent's raw stream, but the agent-managers inside still run on lossy summaries. Legibility for *you* ≠ legibility for the *nodes*. The mitigation (route artifacts through a filesystem, pass references not contents) is a design requirement, not an afterthought.

**Forking is the real unlock — with one honest caveat.** Copying a topology is trivial; the value of an org is mostly its accumulated *state* — memory, warmed-up context, shared scratchpads. Forking a fresh structure is easy; snapshotting and forking a *seasoned* org is the hard, valuable version. What forking enables once solved: evolutionary search over org designs (run N topology variants on one task, measure cost/quality/latency, keep the winner), A/B testing of "management styles," versioned and reversible reorgs, and a marketplace of org templates.

---

## 8. Where the white space is

Plotting prior art on two axes makes the opening obvious.

- **Org structure (fixed → forkable/declarable):** MetaGPT and ChatDev have *rich* roles but *fixed* pipelines. Conductor/Crystal/Vibe Kanban have *no* org model at all (flat parallelism). Nobody offers a declarable, forkable org.
- **Legibility (post-hoc traces → live control surface):** LangSmith/AgentOps give post-hoc traces. The command-center GUIs give window management. Nobody offers Google-Maps-style zoom from whole-org graph to a single agent's live stream, as a steering surface.

The unclaimed intersection — **declarable & forkable org topologies + a real-time legibility command center, built on the Claude Code Agent Teams substrate** — is the project. The MetaGPT lineage proves roles+SOP works but is frozen; the Conductor lineage proves people want to run many agents but only manages windows; Agent Teams supplies the coordination primitives and on-disk state to bridge them; and Windows/tmux gaps mean a cross-platform GUI is genuinely additive. No single existing product sits in that intersection.

---

## 9. Key risks and open questions

The honest hard parts, to confront early rather than discover late:

1. **Topology beyond the star.** Agent Teams is natively a one-level star (no nested teams, fixed lead). Real trees/meshes require orchestrating multiple Claude Code processes yourself. How much can v1 achieve inside the star before that complexity is needed?
2. **Idle vs. thinking vs. stuck.** `TeammateIdle` and idle notifications help enormously, but "stuck / waiting-on-a-permission-prompt / silently looping" is subtler than "stopped." The trustworthiness of this one signal makes or breaks the product.
3. **Coding is a weaker multi-agent fit than research** (Anthropic's own caveat). Parallelizable coding subtasks are fewer; real-time agent-to-agent coordination is immature. The first compelling demos may be research/review orgs, not build orgs.
4. **Token economics gate the use cases.** At ~15× chat tokens, only high-value work justifies a full org. The product must surface live cost and help the user *not* overspend.
5. **Forking stateful orgs is unsolved.** Structure forks cheaply; memory/context does not. v1 likely forks specs, not warmed-up state.
6. **Experimental, moving substrate.** Agent Teams is explicitly experimental with known limitations (session resumption, lagging task status, slow shutdown). Building on it means tracking a moving target.
7. **Steering a live team is a genuine HCI problem.** "See/hide, know who's idle, pop open tools, watch stats" across many agents and monitors is unsolved interaction design, not a solved dashboard.

---

## 10. Sources

- [MetaGPT — GitHub (FoundationAgents/MetaGPT)](https://github.com/FoundationAgents/MetaGPT)
- [What is MetaGPT? — IBM](https://www.ibm.com/think/topics/metagpt)
- [ChatDev: Communicative Agents for Software Development — arXiv 2307.07924](https://arxiv.org/abs/2307.07924)
- [What is ChatDev? — IBM](https://www.ibm.com/think/topics/chatdev)
- [How we built our multi-agent research system — Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Orchestrate teams of Claude Code sessions — Claude Code Docs](https://code.claude.com/docs/en/agent-teams)
- [CrewAI vs LangGraph vs AutoGen — DataCamp](https://www.datacamp.com/tutorial/crewai-vs-langgraph-vs-autogen)
- [Best Multi-Agent Frameworks in 2026 — Gurusup](https://gurusup.com/blog/best-multi-agent-frameworks-2026)
- [Handoffs — OpenAI Agents SDK](https://openai.github.io/openai-agents-python/handoffs/)
- [OpenAI Swarm / Agents SDK — GitHub](https://github.com/openai/swarm)
- [Best Multi-Agent Coding Tools for Claude Code and Codex Users (2026) — Nimbalyst](https://nimbalyst.com/blog/best-multi-agent-coding-tools-2026/)
- [Parallel coding-agent orchestrators — Conductor and the 2026 ecosystem](https://rustman.org/wiki/conductor-parallel-agents/)
- [awesome-agent-orchestrators — GitHub](https://github.com/andyrewlee/awesome-agent-orchestrators)
- [15 AI Agent Observability Tools in 2026 — AIMultiple](https://aimultiple.com/agentic-monitoring)
- [LangSmith — AI Agent & LLM Observability Platform](https://www.langchain.com/langsmith/observability)
- [The Code Agent Orchestra — Addy Osmani](https://addyosmani.com/blog/code-agent-orchestra/)
