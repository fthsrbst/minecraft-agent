# minecraft-agent: Agent Instructions

> **This file is the single source.** `CLAUDE.md` is a symlink to it (`CLAUDE.md -> AGENTS.md`), so editing either
> shows the same content. Do not break the link by replacing `CLAUDE.md` with a regular file.
> If it breaks: `ln -sf AGENTS.md CLAUDE.md`.

## Project

**A learning bot system that can play different games. First prototype: play Minecraft "perfectly".**

- **The Voyager loop:** a curriculum proposes a task → an LLM writes skill code → the code runs in the game → the result is verified independently → the skill enters the library.
- **Decision layers:** L0 plain code (reflexes, emergencies) → L1 fast decision model (TypeSafe Jev or a local model; event-driven tactical choices) → L2 frontier LLM (planning, code) → L3 offline learning.
- **Record a skill:** the player demonstrates once (with spoken or typed narration); the system turns it into a tested, parameterized skill.
- **Generality:** the core knows no game; **Minecraft is a plugin**. Every game connects through the Game Plugin Protocol; the system evolves to other games over time (research.md §5).
- **Selectable autonomy:** in `full` mode the bot **never asks** the user; `approver` / `consult` may ask, but every question has a timeout and the bot never blocks (research.md §5.6).

- Context: Softito AI course, individual project (hard level, #40 "A Learning Agent in Minecraft"). The course delivery is the Minecraft prototype; the architecture prepares for more games.
- Delivery: **2026-11-19**. Deliverables: GitHub repo + README, a working demo (web/CLI), prompt-design and model-choice rationale, an **evaluation report (≥20 tests, success rate, cost, latency)**, a 3–5 minute demo video + presentation.
- Hub project name: `minecraft-agent` (decisions and sessions are written to the hub under this name).

## Documents (docs/)

| File | Purpose | Written by |
|---|---|---|
| [docs/plan.md](docs/plan.md) | **Implementation plan and work tracker** (weeks, work items, PRs, status) | Agents, reviewed by Fatih |
| [docs/research.md](docs/research.md) | **The single research and design document**: Voyager + competitors, Jev, general game agents, record a skill, architecture, model layers, memory, skills, commands, personality, targets, evaluation, risks, external review | Research agents |
| [docs/notes.md](docs/notes.md) | Notes from Fatih and agents, open questions, observations | Everyone |
| [docs/reviews/](docs/reviews/) | Raw external design reviews (synthesis in research.md §14) | Reviewing agents |
| [docs/backlog.md](docs/backlog.md) | **Unfinished work** (written by agents at the end of a session) | Agents |
| `docs/backlog/<topic>.md` | Sub-backlog when a backlog item grows | Agents |
| `docs/spikes/S<n>.md` | Spike reports (hypothesis, setup, numbers, decision) | Agents |

At the start of a session: read `docs/plan.md` (current week), `docs/backlog.md` and the "Open questions" in `docs/notes.md`.

## Decisions

Status: **PROPOSED** = proposed in research.md, not yet confirmed by Fatih · **DECIDED** = confirmed.
When a proposal is confirmed, mark it DECIDED here and save the rationale to the hub with `memory_save type=decision`.

| # | Topic | Status | Content |
|---|---|---|---|
| 0 | Vision | DECIDED (2026-10-15) | A multi-game bot system; the first prototype must play Minecraft "perfectly"; record a skill is a feature |
| 1 | Language / runtime | DECIDED (2026-10-15) | **Core: Python 3.13** (uv, ruff, pyright strict, pytest). **Minecraft plugin: TypeScript** (Node 22, Mineflayer; skill code in TypeScript checked by `tsc`). Doom plugin in Python (ViZDoom). Plugins always run as separate processes over versioned JSON-RPC |
| 2 | Bot library | PROPOSED | `mineflayer@4.39.x` + pathfinder, collectblock, pvp, tool. **Warning:** the plugins are stale (pathfinder 2023-09, pvp 2022-07, tool 2022-05; the viewer falls back to 1.21.4 assets on 1.21.11) → not DECIDED until spike S1 |
| 3 | Minecraft version | PROPOSED | Java **1.21.11**, pinned; changing it requires a skill-library regression run |
| 4 | Server | PROPOSED | Docker `itzg/minecraft-server`, `ONLINE_MODE=false`, localhost only, **RCON on** (used only by the evaluator / scenario builder), the agent's bot is **not op**, `enforce-secure-profile=false` for the proxy |
| 5 | LLM (L2) | DECIDED (2026-10-15, after review) | **Sonnet 5.5 by default** (code writing/repair, planning, skill induction, critic); **Haiku 5.5** for high-volume text (summaries, diary, skill descriptions). The Haiku→Sonnet cascade and Opus 5.5 are measured in spike **S5**; the cascade becomes default only if it is not worse on success and clearly better on time/cost (research.md §6.8) |
| 5b | Budget | DECIDED (2026-10-15) | LLM budget is not a constraint; quality first. Cost is still measured on every call (for the report) |
| 6 | Verification | PROPOSED | Deterministic predicate first, then an L1 Noul, an LLM critic last. Predicates are written **before and independently of the code** (predicate-first synthesis) and tested on negative examples; undecidable = `unknown`, never success. A critic opinion is never treated as verified success |
| 7 | Skill storage | PROPOSED | SQLite + local embeddings + top-k; skill code is also stored as `.ts` files, published atomically |
| 8 | Code execution | PROPOSED (changed after review) | `node:vm` is **not enough** (no async timeout, the event loop can lock). Skill code runs in a separate executor with no keys, restricted fs/network and resource limits; game actions go through a permission-checked primitive broker; an external watchdog; static rules (no loop without `await`, no `bot.chat('/…')`). Skills are TypeScript checked by `tsc` (research.md §5.2, §14) |
| 9 | Game plugins | DECIDED (Minecraft is a plugin; the system evolves to other games) · details PROPOSED | **Thin mandatory core** (`handshake, observe, act, runSkill, interrupt, reset, events`) + optional capabilities (predicates, knowledge, scenario, record, memory extractors, visibility…). The contract matures inside the Minecraft plugin and is tested with a ViZDoom spike (S8). Generality metrics: plugin development time, duplicated code, escape hatches, behavioral parity (research.md §5.2–5.5) |
| 9b | Autonomy | DECIDED (2026-10-15) | The autonomy level is an **option**: `full` (never asks), `approver` (asks for risky actions), `consult` (consults). A question never blocks the bot (timeout + default). **Communication preference is separate from permission:** a timeout never grants permission; the risky step is skipped, an alternative is chosen, or the task ends safely. Defaults: AFK `full`, teaching `consult`. Measured in `full`: wrong assumptions, later corrections, irreversible actions (research.md §5.6) |
| 10 | L1 | PROPOSED (changed after review) | **Emergencies in L0** (event → action ≤100 ms). L1 = event-driven tactical choice + language-semantic points (command → skill, narration type, skill rerank, stagnation), p95 ≤300 ms. New L1 points start in **shadow mode**. `DecisionClient` at delivery: rules + Jev (key available) + 1 local candidate; thresholds per `(question, provider, version, projection)`; numeric/geometric work in code. Unsloth ↔ TypeSafe SDK compatibility not verified |
| 10b | Model layers | PROPOSED | L0 reflex code → L1 decision model → L2 frontier LLM → L3 offline (labeling, fine-tuning). Escalation ladder and decision-point map: research.md §6 |
| 10c | Question registry | PROPOSED | Every L1 decision point is a versioned question definition (instructions, criteria, state projection, threshold, fallback); every call is logged → benchmark + fine-tuning data |
| 10d | Value test | PROPOSED | An L1 point that does not beat the hand-written L0 rule for the same decision, by measurement, stays in L0 |
| 11 | Recording (Minecraft) | PROPOSED | `minecraft-protocol` proxy; vanilla client → proxy → server; packets → semantic events (request / ack / observed / inferred kept apart) → subgoals → skill → verification on unseen terrain |
| 11b | Narration | DECIDED (2026-10-15) | Spoken **or** typed. Text: `//`-prefixed notes in in-game chat (captured by the proxy). Voice: local Whisper, aligned to events with timestamps |
| 11c | Recording output | PROPOSED | Two artifacts: an executable code skill + an intent card (when, inputs, rules, stop conditions, completion predicate). Depends on autonomy: `full` asks nothing (assumptions reported, Save/Update/Discard automatic); `consult` asks timed follow-ups. Automatic verification in fresh worlds (research.md §4.3, §4.6) |
| 11d | Game memory | PROPOSED | Not one RAG: places, resource state, chest memory, event log + RAG, lessons/decisions (all in scope; order in plan.md). Location/resource questions in code. Identity: `world_instance_id + episode_id + reset generation` (**the seed is not an identity**) (research.md §7) |
| 11e | Hardware | DECIDED (2026-10-15) | `fatih-pc` RTX 5070 Ti 16 GB: L1 training + local serving, embeddings, Whisper. Fatih installs the real Minecraft client |
| 11f | Skill design | PROPOSED | 5 levels (reflex → primitive → basic → composite → routine); a contract for every skill (parameter schema, pre/postcondition predicates, side effects, typed failures, cancel/resume, risk, duration); lifecycle draft → verified → trusted → retired, repairs as candidate versions; scenario tests + regression; a bounded `obtain(item, n)` recipe solver; a hand-written starter core (research.md §8) |
| 11g | Commands / pipelines | PROPOSED | Natural language, voice and visual pipelines compile into one **task graph** (Task IR: skill, sequence, fallback, loop, condition, trigger, guard, budget, report). Deterministic `#command` parser first, then L1, then L2. Read-back; approval only in `consult` (timed); persistent state; AFK summary (research.md §9) |
| 11h | Personality | PROPOSED | Optional persona + bounded mood + narration + diary + highlights. Player commands always first; off in "work mode". Post-loss recovery and stagnation detection are independent of personality and always on (research.md §10) |
| 12 | Delivery scope | DECIDED (2026-10-15) | **Everything in the vision is in scope** (voice, editor, approver/consult, personality, episodic RAG, L3 fine-tuning); the second game **Doom comes after delivery**. The reviewers' schedule risk is managed by **ordering**: first the core that measures the main claim, with the measurement updated at every milestone, then extensions (plan.md) |
| 13 | Action arbiter | PROPOSED | A single action owner: skills, L0, L1 and triggers propose; the arbiter picks by priority (emergency safety > player command > trigger > task), manages resource ownership, waits for interrupt acks, discards late results of interrupted work, re-checks preconditions before resuming (research.md §6.4) |
| 14 | Evaluation protocol | PROPOSED | Pre-registration; learning seeds ≠ test seeds; frozen library during testing; given and learned skills reported separately; ≥20–30 paired runs in the main arms + McNemar/bootstrap; one main hypothesis first; mostly short RCON scenarios; a wall-clock budget (research.md §11.1) |
| 15 | Perception and authority | DECIDED (visibility, 2026-10-15) + PROPOSED (authority) | **Two visibility modes:** fair mode (default for evaluation/report; only blocks in line of sight or exposed to air) + full-knowledge mode (selectable for AFK); the mode is written into every result file. Authority: the agent is not op; scenario/reset/ground truth only for the evaluator (RCON); in-game text is data, never instructions |
| 16 | Main claim | DECIDED (2026-10-15) | **Learning by playing:** a learned skill library reduces time and LLM calls in unseen worlds without lowering success. Learning from demonstration and AFK reliability are supporting results (research.md §11) |
| 17 | Definition of "perfect" | DECIDED (2026-10-15) | **Tiered.** Main: easy + fair mode + unseen seeds → diamond pickaxe; survive 3 in-game days on normal; a 25-task set. Stretch: Ender Dragon in an unknown world, survival, no prepared route. Companion behavior via AFK tasks (research.md §11) |
| 17b | Targets | DECIDED (2026-10-15) | The target table in research.md §11 is accepted (≥8/10 seeds, ≥90% task set, ≤1 death in 3 days, ≤100 ms / p95 ≤500 ms reaction, ≥4/5 demonstrations, …), always reported with confidence intervals |
| 18 | Recording order | DECIDED (2026-10-15) | **Phased:** v1 deterministic blueprint + subgoal macro; v2 behavioral skills (farming, combat) via L2, verified on unseen terrain. Both in scope (research.md §4.6) |
| 19 | Mindcraft | DECIDED (2026-10-15) | **Borrow parts, do not build on top:** tested skills/world helpers, Mineflayer plugin patches, the ViaProxy setup, the task JSON format go into the Minecraft plugin. MIT; every borrowed file is recorded with source and version. The core is ours (research.md §5.4) |
| 20 | Multi-agent | DECIDED (2026-10-15) | A planned future extension (after delivery): per-agent identities, shared/private memory, a world coordinator, structured inter-agent messages. Keep identities per agent from the start (research.md §5.5) |
| 21 | Language of the repository | DECIDED (2026-10-15) | **Everything in the repository is English**: documents, code, comments, commit messages, PRs, templates. Conversation with Fatih may be Turkish |
| 22 | Work tracking | DECIDED (2026-10-15) | Work is tracked in **`docs/plan.md`**, not in GitHub issues. Code still goes through PRs reviewed by Fatih |

**External review (2026-10-15):** Claude Opus 5.5 and GPT-6-Astra independently critiqued the whole design. Shared findings are in the decisions above; questions needing Fatih's decision were decided on 2026-10-15 (research.md §14.4). Raw reports: `docs/reviews/`. The coding phase starts with the spikes in research.md §14.6, scheduled in plan.md.

## Architecture (target)

Details and diagrams: [docs/research.md §5](docs/research.md). Modules (no code yet):

Core / host (`core/`, **Python**, game-independent; no game, block or item names inside):
- `orchestrator`: the autonomy engine; learn / run-task / eval loops; decision log
- `plugins`: plugin loader, handshake, capability negotiation, protocol versioning, conformance kit
- `planner` (L2): curriculum, action (writes skill code), critic (fallback), model routing
- `decisions` (L1): `DecisionClient` + providers (typesafe, unsloth-local, logit-local, nli-local, llm-structured, rules), question templates + registry, escalation ladder
- `arbiter`: single action owner; priorities, resource ownership, interrupt acks, discarding stale results
- `monitor`: L0 emergency reflexes + event-driven L1 tactics → proposals to the arbiter
- `training` (L3): scenario generation (through the plugin's scenario builder), labeling, datasets, S1-Bench
- `skills`: skill library; contracts, lifecycle, test runner, retrieval, versions, repair
- `tasks`: task graph (Task IR), `#command` parser framework, NL/voice compiler, behavior-tree runtime, triggers, persistent state, scheduling
- `memory`: places, resource state, storage memory, event log + RAG, lessons/decisions; freshness and forgetting
- `recording`: game-independent stages: abstract → clean → segment → induce → verify
- `persona`: optional personality; mood, narration, diary, highlights
- `executor`, `verifier`, `telemetry`, `ui` (CLI + web dashboard shell, voice)

Game plugins (`plugins/<game>/`, each a separate process with a manifest + components, research.md §5.2):
- `plugins/minecraft` (**TypeScript**): Mineflayer adapter, primitives, isolated skill executor + primitive broker + watchdog, predicates, knowledge provider (`minecraft-data` recipe graph → `obtain`), vocabulary, memory extractors, visibility filter, RCON scenario builder (`/give /tp /summon /fill`), recording proxy, starter skills, L1 question pack, prompt fragments, `#command` vocabulary, prismarine-viewer panel
- After delivery: `plugins/doom` (Python, ViZDoom), then `plugins/retro`, `plugins/desktop-pixel`

## Workflow

Repository: [`fthsrbst/minecraft-agent`](https://github.com/fthsrbst/minecraft-agent) (public). **Claude writes the code; Fatih reviews it and learns from it.** The goal is also to learn a professional workflow.

1. **Work comes from `docs/plan.md`.** Each item has an ID (`P1.4`), goal, deliverables, acceptance criterion and planned PRs. Update its status in the same PR.
2. **Branch:** `p<week>.<item>-<short-name>` (e.g. `p1.4-plugin-protocol`). No direct commits to `main`.
3. **Small PRs.** One reviewable step per PR, ideally under ~400 changed lines. The description follows `.github/pull_request_template.md`; the **"Learning notes"** section is mandatory: which concepts, why this approach, where to start reading.
4. **Verify before review:** tests, lint and type checks pass locally; the commands and their output go into the PR. Anything not verified is labeled "not verified".
5. **Review:** Fatih reviews, asks questions or requests changes. The agent answers and pushes fixes to the same branch.
6. **Merge:** only after Fatih approves. Squash merge; imperative commit subject, ≤ 72 characters.
7. **Attribution:** commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; PR descriptions end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
8. **Spikes** write `docs/spikes/S<n>.md` with a success criterion fixed before running.
9. Unfinished work goes to `docs/backlog.md`.

## Rules

- **Phase (from 2026-10-15): coding phase**, following `docs/plan.md`. Delivery 2026-11-19.
- **Everything in the repository is English.**
- Code standards:
  - **Python (core):** 3.13, environment with `uv`, `ruff` (lint + format), `pyright` strict, `pytest`. snake_case module names.
  - **TypeScript (Minecraft plugin):** strict, npm, prettier + eslint, vitest, kebab-case file names.
  - Comments explain constraints the code cannot show, not what the code does.
- **Security:** LLM-written code runs on this machine. **Never connect the agent to a public server**; only the local Docker server.
- **Measurement is mandatory:** every code path that calls an LLM or a decision model goes through telemetry (tokens, cost, latency, trace id). The report is generated from it.
- **Reproducibility:** experiments and evaluation runs use fixed seeds + hard resets; the seed, `world_instance_id`, visibility mode and model names are written into every result file.
- Secrets (API keys) only in `.env`; `.env` is never committed; keep `.env.example` current.
- External service calls need a timeout and a meaningful error message; never swallow errors.
- When a skill or primitive changes, rerun the related evaluation tasks; write the result to the PR, backlog or notes.
- **The core stays game-independent:** no `minecraft`, `mineflayer`, block or item names in `core/`; everything game-specific lives in a plugin. If the core seems to need something game-specific, that is a **contract gap**: extend the plugin contract generically (bump its version), never put game code in the core.
- **Autonomy rule:** every flow that asks the user something must depend on the autonomy level (it never runs in `full`) and must have a **timeout + default answer**. No flow may wait indefinitely for an answer. A timeout never grants permission.
- New research goes into `docs/research.md` as a section (no separate research files).

## End of session

1. Write unfinished work to `docs/backlog.md` (format in that file) and update the item status in `docs/plan.md`.
2. Add lasting observations or ideas to `docs/notes.md` → "Agent notes".
3. Hub: `session_log` + `project_update` if the focus changed (project: `minecraft-agent`).
