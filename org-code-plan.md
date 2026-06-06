# Org-Code: Evolution Plan (repo-grounded)

*Evolve `parallel-agents` from a fixed specialist pipeline into a forkable "org-as-code" system, and upgrade the PySide6 Desktop Office into a real legibility command center — built on the code you already have.*

Companion to `org-code-research.md` · Reconciled against the `parallel-agents` repo · June 2026

---

## 0. What changed in this version (read first)

The earlier draft of this plan was written greenfield, before reading your codebase. Two recommendations in it were wrong for your repo and are **superseded here**:

1. **Substrate.** The old plan said "build on top of Claude Code *Agent Teams*." You don't need to. Your engine **is** the substrate: a Python `asyncio` fan-out pipeline (`src/parallel_agents/pipeline.py`) running specialist agents over `claude-code-sdk` (`agents/base.py`, `agents/planner.py`), with a Claude CLI fallback (`claude_cli_fallback.py`). Agent Teams stays in this plan only as a **reference design** for primitives (mailbox, idle hooks, on-disk team state) — not as a dependency. This also deletes the biggest risk in the old plan ("programmatic control of an experimental prompt-driven substrate"): you already control your pipeline programmatically because you wrote it.

2. **Shell.** The old plan proposed a new local web app (Vite + React + Node/Bun + react-flow). You already ship a cross-platform **PySide6 desktop** (`parallel-agents-desktop`, PyInstaller `.exe`) with a live run page. Introducing React/Node would violate `TECH_STACK_POLICY.md` (new framework ⇒ documented `TechStackDecision`). So the command center is an **extension of the existing Qt app**, and the signature org-graph view is **Qt-native (QGraphicsView/QGraphicsScene)** unless you deliberately file an RFC for a web view.

Everything below is rebuilt on those two corrections and cites real modules so it slots into your existing `ROADMAP.md`.

---

## 1. Positioning

**One-liner:** turn `parallel-agents` from *one frozen org shape* into *a forkable organization you can author, run, watch live, and A/B test* — Google-Maps-for-your-agent-org, zoom from the whole org graph down to a single agent's live token stream, all inside the Desktop Office you already ship.

**What it is:** two new layers on top of the existing engine.
- A **legibility plane**: upgrade the Desktop Office (`desktop/`) from a fixed worker grid driven by parsed status strings into a trustworthy, zoomable, event-driven command center with live idle/stuck detection and live cost/budget.
- An **org-as-code layer**: lift your flat, env-driven `PipelineConfig` into a declarable, forkable `org.yaml` (roles + topology + rules + budget) that compiles into a run — and compare two forks with the eval harness you already built.

**Who it's for (initial wedge):** exactly the user in `VISION.md` — the Solo Builder / Small Team already running your pipeline who has outgrown "8 fixed workers, one shape" and wants to *see*, *steer*, and *redesign* the org. (You are on Windows; the existing PySide6 + `.exe` path already serves that, unlike Mac-only / tmux competitors.)

**Why now:** the substrate is done and mature (`PROJECT_STATUS.md`: parallel pipeline, evidence store, cost tracker, eval compare, GitHub-first flow, desktop). The two missing things — *legibility you can trust* and *an org you can fork* — are the open white space (research §5–§8), and both are short hops from code that already exists.

---

## 2. Where you actually are (the repo as substrate)

Your pipeline is a textbook "Code = SOP(Team)" frozen org — the exact MetaGPT/ChatDev limitation the research identifies (research §2–§3). That's not a criticism; it's the thing you're about to make forkable. Concretely, the org is frozen in three places:

| Frozen thing | Where it lives | Why it blocks "org code" |
|---|---|---|
| **The roster** | `pipeline.py::_load_workers()` hardcodes `WORKER_REGISTRY` with 8 classes (`SecurityWorker`…`DocsWorker`). | Roles are compiled in, not declared. You can disable one via config, but you can't add `critic`, fork the set, or diff two rosters. |
| **The shape** | `Pipeline.run()` is a fixed 4-phase sequence: `run_planner` → `split_tasks` → workers (`asyncio.Semaphore` fan-out in `_run_batch`) → `run_judge`. | The topology is a one-level **star** (lead-planner → flat workers → judge). No trees, no nested teams, no escalation — and it's expressed in control flow, not data. |
| **The "spec"** | `config.py`: `PipelineConfig.workers: dict[str, WorkerConfig(enabled, model, max_turns, timeout)]`, driven by `PA_` env vars / `.env`. | This is an *embryonic* org spec — roles with models — but it's flat (no topology, no rules, no budget) and env-shaped, so it can't be authored, forked, or diffed as one artifact. |

The good news is how much of the hard plumbing already exists:

- **Per-agent events already stream.** `evidence_store.py` exposes `append_trace(agent_name, entry)` writing structured JSONL (`{phase, status, ts, batch, workers, event, ...}`) per agent, in both `EvidenceStore` and `SQLiteEvidenceStore` (with a `traces` table + `load_traces`). The legibility plane has a real event source today.
- **Per-agent cost already tracked.** `cost_tracker.py::PipelineCostTracker.record_usage(...)` captures model, input/output/cache tokens, `cost_usd`, `duration_ms`; `MODEL_PRICING` covers opus/sonnet/haiku; `summary()` gives per-agent + totals. Live cost meters are already fed — what's missing is *enforcement* (a budget guard).
- **Fork-comparison already exists.** `eval_harness.py::compare_evaluation_results(baseline, candidate, …)` returns an `EvaluationComparison` with deltas (`speed_gain_median_delta`, `acceptance_rate_delta`, `regression_rate_delta`), plus `EvaluationBreakdown` for cost/time buckets. "Fork A vs fork B" is mostly a feeding problem, not a building problem.
- **The desktop already runs and watches a pipeline.** `desktop/pages/runs_page.py` (`RunsPage`) runs the pipeline on a background `AsyncJob` (`services/workers.py`), streams `on_status` strings into an Activity log, and updates a `WorkerGrid` (`widgets/worker_grid.py`) of tiles with idle/running/done/error states.
- **The UI is already decoupled from the engine.** `desktop/services/engine.py` (`EngineService`) is an explicit facade "so we can swap in-process calls for HTTP-to-gateway later without touching widgets." That seam is exactly where the org-spec compiler and the event bus plug in.

The one real weakness to fix early is **how the desktop learns status**: `RunsPage._apply_worker_status_from_message()` infers each agent's state by **string-matching** the human-readable `on_status` messages (`"Planning:"`, `"Splitting tasks"`, `"Batch …"`, `"Judge is"`, `"Done. Run ID:"`). That's the brittle status-scraping the research warns is the make-or-break signal (research §9). You already have the cure on disk (`append_trace`); you're just not consuming it.

---

## 3. The two layers (build in this order)

**Layer 1 — Legibility plane.** Make the running org trustworthy and legible inside the existing Qt app: event-driven status (kill the string parsing), idle/stuck detection, live per-agent token + dollar meters, and a budget guard. This de-risks the make-or-break signal first and is a natural extension of Phase 4 ("Local Desktop Office") which `ROADMAP.md` already lists as in-progress.

**Layer 2 — Org-as-code.** Lift `PipelineConfig` into a declarable `org.yaml` (roles, topology, rules, budget) that **compiles into a run**, then fork/diff/compare. It only becomes trustworthy *because* Layer 1 exists — you can watch a fork run and see what changed.

Order matters: Layer 1 turns your existing run page into something worth watching; Layer 2 gives people a reason to run many variations and watch them.

---

## 4. The central architectural decision (reframed around your code)

The fork that decides scope is the same one from the research, but stated in *your* terms:

**Your engine is natively a one-level star.** `Pipeline.run()` hardwires planner → fan-out → judge. You cannot express a tree, a mesh, or nested teams by editing config alone — the shape is in control flow.

| Path | What you build on your engine | Cost |
|---|---|---|
| **A — Make the star forkable** | Keep the single `Pipeline`. Externalize the roster + models + rules + budget into `org.yaml`; the compiler builds `WORKER_REGISTRY` and `PipelineConfig` from it. "Org shapes" = role/rule/budget variations on the star. | Topology stays a star; trees/meshes are faked as role sets, not real routing. |
| **B — Orchestrate multiple pipelines** | Run *several* `Pipeline` instances (or processes), each a star, wired together via the evidence store + a routing/escalation layer, to compose trees/clusters/mesh. | Much more engineering: cross-pipeline routing, escalation, shared state, budget across pipelines. |

**Recommendation: A for v1, B as the Phase-bet.** Ship forkable role-orgs on the star first — it's real, it's days-to-weeks on code you own, and it produces the demo (fork the org, watch both, compare cost+output). Only after that's compelling do you build the multi-pipeline orchestrator that unlocks true topologies — the genuinely novel, defensible part. Don't start with B; you'd spend months on orchestration before learning whether the legibility surface lands.

This maps cleanly onto `org-code-research.md` §5/§9 and onto your `ROADMAP.md`: Path A is a Phase-4-adjacent feature; Path B is a new late phase.

---

## 5. Architecture (v1, Path A — grounded in real modules)

```
┌──────────────────────────────────────────────────────────────┐
│  Desktop Office  (PySide6 — desktop/app.py, main_window.py)    │
│  • Org graph view  (NEW: QGraphicsView; replaces WorkerGrid    │
│    fixed grid in widgets/worker_grid.py) — zoom org→agent      │
│  • Agent tiles: status, current subtask, tokens, $, duration   │
│  • Activity stream (pages/runs_page.py) — fed by EVENTS now     │
│  • Org editor (NEW page): author/fork org.yaml, diff, compare  │
└───────────────▲───────────────────────────┬──────────────────┘
                │ Qt signals (live)           │ actions
┌───────────────┴───────────────────────────▼──────────────────┐
│  EngineService facade  (desktop/services/engine.py)            │
│  • run_pipeline(...)  • NEW: compile_org(org.yaml)→config       │
│  • NEW: event tap over evidence_store traces (not string parse) │
└───────────────▲───────────────────────────┬──────────────────┘
                │ structured events           │ launches
┌───────────────┴───────────────────────────▼──────────────────┐
│  Engine  (src/parallel_agents/)                                │
│  Pipeline.run(): run_planner → split_tasks → workers → run_judge│
│  evidence_store.append_trace(...)  ·  PipelineCostTracker       │
│  NEW: structured status events + budget guard in the run loop  │
│  Substrate: claude-code-sdk query() (+ claude_cli_fallback)    │
└────────────────────────────────────────────────────────────────┘
```

The key integration insight, restated for your repo: **you don't scrape status strings — you already emit structured per-agent trace events.** Route the desktop off `append_trace` and idle/stuck detection becomes reliable instead of a guess.

---

## 6. Layer 1 — Legibility plane (MVP-1), as concrete edits

Each item names the file it touches so it's a work order, not a wish.

**6.1 Promote status to a structured event (engine).** Today `Pipeline.run()` calls `on_status(str)` and writes rich `append_trace` entries in parallel. Add a typed event alongside the string: extend the status callback to also emit a small `AgentEvent` (`agent`, `phase`, `state ∈ {planning,running,idle,blocked,done,error}`, `subtask_id`, `ts`, `tokens`, `cost_usd`). Source the data you already compute in `_run_batch` (`worker_started`/`worker_completed` already go to `append_trace`). This is the single highest-leverage change — everything else reads from it.

**6.2 Consume events, delete the string parser (desktop).** In `desktop/pages/runs_page.py`, replace `_apply_worker_status_from_message()` (the `startswith("Planning:")` / `"Batch …"` matching) with a handler over the new `AgentEvent`. The Activity log can still print human strings; tile state must come from events.

**6.3 Trustworthy idle/stuck detection (engine + desktop).** "Idle" = a worker that has claimed a subtask but produced no trace event for *N* seconds; "stuck/looping" = repeated identical events or retry churn (you already log retries in `execute_with_retry`). Surface a distinct `blocked`/`stuck` tile state so the screen tells you *who needs you* — the thing the research calls the killer signal (research §9.2) and the thing the current parsed-status UI can't do.

**6.4 Live token/$ meters per agent (desktop).** `PipelineCostTracker.summary()` already yields per-agent `input_tokens/output_tokens/cost_usd/duration_ms`. Bind those onto each tile and a run-total header. No new engine work — just surface what `cost_tracker.py` already computes.

**6.5 Budget guard (engine — new behavior).** `PipelineCostTracker` tracks but does not *enforce*. Add a `budget` to the run (tokens and/or USD) checked between batches in `Pipeline.run()`; on breach, stop scheduling new subtasks and emit a `budget_exceeded` event. This is the `org.yaml` `budget.stop_on` hook (Layer 2) and a real feature given multi-agent's ~15× cost reality (research §4).

**6.6 The org graph view (desktop — the signature interaction).** Replace the fixed 4-column `WorkerGrid` (`widgets/worker_grid.py`, `WORKER_ROLES` hardcoded) with a `QGraphicsView`/`QGraphicsScene` graph: planner at the root, workers as children, judge as the sink, edges = the dependency batches `split_tasks` produced. Zoom levels: **org → team → agent → live stream**. Keep it Qt-native to stay inside `TECH_STACK_POLICY`.

**MVP-1 success test:** start a real run from the desktop; glance at the screen and instantly know which agent is working, which is idle/blocked, how many tokens/dollars each has burned, and how close you are to budget — with status coming from events, not parsed strings.

---

## 7. Layer 2 — Org-as-code (MVP-2), as concrete edits

**7.1 The spec.** A YAML artifact that supersets today's `PipelineConfig`. Start role-level on the star; reserve `topology` for Path B.

```yaml
org:
  name: research-pod
  topology: star            # v1: star  (v2: tree | mesh | clusters)
  budget:
    usd: 5.00               # enforced by §6.5 budget guard
    stop_on: "budget_exceeded | task_complete"
  rules:
    plan_gate:  "require plan approval for code-writing roles"   # maps to permission_mode
    escalation: "worker error > 2 retries -> notify judge"        # maps to execute_with_retry
    decision:   "judge owns final synthesis"                      # maps to run_judge
  roles:                    # compiles into WORKER_REGISTRY + PipelineConfig.workers
    - id: planner
      type: planner
      model: opus
    - id: security
      type: security        # -> SecurityWorker (agents/workers/security.py)
      model: sonnet
    - id: critic            # NEW role = new BaseWorker subclass + system prompt
      type: review
      model: sonnet
      prompt: "Challenge the others' conclusions; surface what they missed."
    - id: judge
      type: judge
      model: opus
```

**7.2 The compiler (engine — new module, `org_spec.py`).** `compile_org(org.yaml) -> PipelineConfig` + a roster the pipeline loads. Today `_load_workers()` hardcodes the 8 classes; change it to build `WORKER_REGISTRY` from the spec's `roles`, mapping `type` → existing `BaseWorker` subclass and overriding `model`/prompt. `BaseWorker` already takes a `WorkerConfig` and a `system_prompt()`, so a declared role with a custom `prompt` is a thin subclass/factory — no engine rewrite. Wire `rules` to the knobs that already exist: `plan_gate` → `permission_mode`, `escalation` → `execute_with_retry` thresholds, `budget` → §6.5.

**7.3 Fork = copy the file, change one field, re-run.** Flip a `model`, add `critic`, tighten `budget` — that's "forking an agentic org" in one diff. Surface it in a new desktop **Org** page: edit, fork, side-by-side diff.

**7.4 Compare two forks (mostly already built).** Run org-A and org-B on the same task; feed both into `eval_harness.compare_evaluation_results(...)` and render the existing `EvaluationComparison` deltas (speed/acceptance/regression) + `EvaluationBreakdown` (cost/time) in the desktop's existing comparison drill-down. The eval harness was built to compare baseline-vs-candidate *runs*; here the two candidates are two **org designs**.

**MVP-2 success test:** changing the org is a single file edit; one click compiles and runs it; the difference between two forks is visible on cost + output, side by side.

---

## 8. Roadmap (slotted into your existing ROADMAP.md)

Your `ROADMAP.md` Phases 0–3 are mostly complete; Phase 4 (Local Desktop Office) is in progress; 5–6 partial. This work attaches like so:

| Phase | Fits where | Key deliverables (file-level) |
|---|---|---|
| **0 — Spikes** (days) | new, pre-work | Add `AgentEvent` to `Pipeline.run` + emit from `_run_batch`; tap it in `runs_page.py`; prove idle detection from events on one real run; prototype `QGraphicsView` tile. |
| **4.x — Legibility plane** | extends Phase 4 (in progress) | §6.1–§6.6: event-driven status, idle/stuck states, per-agent $/token tiles, budget guard, org-graph view replacing `WorkerGrid`. |
| **7 — Org-as-code** | new phase | `org_spec.py` schema + `compile_org`; spec-driven `WORKER_REGISTRY`; declared `critic`-style roles; Org editor page; two-fork compare via `compare_evaluation_results`. |
| **8 — Real topologies** | new phase (the bet) | Path B: multi-`Pipeline` orchestrator; cross-pipeline routing + escalation through the evidence store; `topology: tree|mesh|clusters`; "run N orgs, rank" via the eval harness. |
| **9 — Polish/dist** | extends existing packaging | Org-template library; replay from `evidence_store` traces; multi-monitor; ship in the existing PyInstaller `.exe`. |

This respects your stated near-term priority (finish Phase 4) by making Layer 1 a *continuation* of it, and defers the expensive Path B until the cheap, novel part has proven demand.

---

## 9. Tech-stack discipline (per TECH_STACK_POLICY.md)

- **No new runtime/framework for v1.** Everything above is Python + PySide6 + the libs already in `pyproject.toml` (`claude-code-sdk`, `pydantic`, `pydantic-settings`, `click`, `rich`; `PySide6` desktop extra; `fastapi` gateway extra). YAML parsing is the only likely new dependency (small, standard) and fits the "approved unless a requirement can't be solved cleanly" rule.
- **The one decision that needs an RFC:** if you ever want the org-graph as a *web* view (richer than `QGraphicsView`), that's a `TechStackDecision` (React/Vite/etc.). Default for v1 is Qt-native — no RFC, ships in the `.exe`.
- **Keep the engine seam.** `EngineService` already isolates UI from engine; the compiler and event bus plug in there, so a future gateway/HTTP or web shell doesn't ripple into widgets.

---

## 10. Hard problems to confront first (not last)

1. **Trustworthy idle/stuck detection.** The product's value rides on this. Build it in Phase 0 off the `append_trace` event stream; do **not** ship the string-parsing path forward.
2. **Topology beyond the star.** Native shape is a star in `Pipeline.run` control flow. Real trees/meshes = Path B multi-pipeline orchestration. Know it's Phase 8; scope v1 as forkable role-orgs.
3. **Budget enforcement.** `PipelineCostTracker` measures but doesn't stop. The budget guard (§6.5) is a feature, not a nice-to-have, at ~15× cost.
4. **Spec ↔ engine fidelity.** The compiler must produce exactly what `_load_workers`/`PipelineConfig` expect, or runs silently diverge from the authored org. Treat `org.yaml` → `PipelineConfig` as a tested boundary (round-trip + schema validation), behind the `EngineService` seam.
5. ~~Programmatic control of an experimental substrate.~~ **Dissolved.** You own the pipeline; there is no Agent Teams unknown to spike.

---

## 11. First steps (this week)

1. In `Pipeline.run()` and `_run_batch` (`pipeline.py`), emit a typed `AgentEvent` next to each existing `append_trace`/`on_status` call — start with `planning/running/done/error` plus the token/cost you already record.
2. In `desktop/pages/runs_page.py`, add an event handler and start retiring `_apply_worker_status_from_message`; drive `WorkerGrid` tiles from events.
3. Add idle detection: flag any claimed-but-silent worker after N seconds as `idle/blocked`; prove it on one real run.
4. Bind `PipelineCostTracker.summary()` per-agent numbers onto the tiles + a run-total header.
5. Prototype the `QGraphicsView` org graph (planner→workers→judge, edges from `split_tasks` batches) behind a feature flag, beside the current grid.

Nail those and the legibility plane (Phase 4.x) is mostly wiring you've already proven — and the org-as-code compiler (Phase 7) has a trustworthy surface to be born into.

---

## 12. Open decisions to make before coding

- **Name the v1 honestly.** Is "star-with-forkable-roles" enough to call it *org code*, or do you reserve that term until Path B ships real topologies? (Recommendation: call v1 "forkable role-orgs"; reserve "org topologies" for Phase 8.)
- **Audience first cut.** Research/review orgs (your pipeline's strongest fit) or code-writing orgs? Research is the safer first demo (research §4/§9.3).
- **Graph rendering.** Qt-native `QGraphicsView` (no RFC, in-policy, ships in `.exe`) vs. a web view (needs a `TechStackDecision`). Default Qt for v1.
- **Where the org spec lives.** A new top-level `org.yaml`, or inside the existing `.parallel-agents/` project workspace next to `runs/`, `artifacts/`, `memory/`? (Recommendation: inside the workspace, so forks are per-project and versioned with the rest of the office state.)
