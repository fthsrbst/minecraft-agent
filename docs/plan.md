# Implementation Plan: the narrowed prototype

> Delivery: **2026-11-19** (5 weeks from 2026-10-15). This document replaces GitHub issues as the work tracker.
> Design and rationale: [`research.md`](research.md). Decisions and rules: [`AGENTS.md`](../AGENTS.md).

## Scope: every part of the vision, each in its thinnest working form

The full design in `research.md` stays the long-term target. For the course delivery we build a **narrowed
prototype**: every headline of the vision appears in the demo, but each one in its simplest version that still works
end to end. Depth (sandbox hardening, statistics, L3 fine-tuning, voice, Doom) moves to "Later" at the bottom.

| Vision part | In the prototype | Deferred to "Later" |
|---|---|---|
| Server + bot | Local Docker server, the bot joins and chats | prismarine-viewer |
| Game plugin architecture | Python core ↔ TypeScript plugin as a separate process, newline-delimited JSON-RPC over stdio (`handshake`, `observe`, `act`, `runSkill`, `events`); the core knows no game names | Conformance kit, capability negotiation, Doom |
| Voyager loop | Task → acceptance predicate → LLM writes skill code → plugin runs it → predicate verifies → skill saved (≤ 3 attempts with error feedback) | Advanced curriculum |
| Safe execution | Skill code runs in a child process with a timeout and a small deny-list (`require`, `process`, `bot.chat('/…')`) | Primitive broker, resource limits, `tsc` gate (skills are JavaScript for now) |
| Skill library | JSON/SQLite store + keyword search, reuse in later tasks | Lifecycle, candidate versions, embeddings |
| L0 reflexes | Flee or fight a nearby hostile; eat when hungry | Measured ≤ 100 ms guarantee, full arbiter |
| L1 decision model | One decision point (command text → skill) with Jev, falling back to a rule | Question registry, shadow mode, local models |
| Commands | `#goto`, `#mine`, `#follow`, `#stop`, plus free text → L2 | Task IR, behavior trees, AFK pipelines |
| Game memory | Named places (home, mine) | Chest memory, resource state, episodic RAG |
| Record a skill | Player writes `//` notes in chat while acting; the bot watches block and inventory events; L2 turns the recording into a skill; it is replayed and verified | Recording proxy, voice narration, behavioral skills |
| Autonomy | `full` / `consult` flag; a question has a timeout and a default, and a timeout never grants permission | `approver` |
| Personality | A persona in the chat prompt | Mood, diary, highlights |
| Evaluation | **≥ 20 RCON scenario tests**, success rate, cost and latency from telemetry, with vs without the learned library | Pre-registration, McNemar/bootstrap |
| Demo | CLI + a small web page | Dashboard |

## How we work

- **Claude writes the code; Fatih owns the architecture and the logic.** (Revised 2026-10-15: the earlier
  "Fatih writes the code" mode was dropped to keep the delivery date.) Fatih must be able to explain how every part
  works and why it is built that way, without having typed every line.
- **Each PR teaches the design:** its learning notes explain where the piece sits in the system, the data flow, the
  key decisions and their trade-offs, and where to start reading.
- **Every code change goes through a pull request.** Fatih reviews it, asks questions
  and requests changes; Claude applies them. Nothing is merged without Fatih's approval.
- **Python first.** The core (Python) carries most of the logic. The TypeScript plugin stays a thin layer over
  Mineflayer.
- **This plan is the tracker.** Each work item has an ID (`P1.3`), a goal, deliverables, an acceptance criterion and
  a learning focus. The status column is updated in the same PR that changes it.
- **Branches:** `p<week>.<item>-<short-name>` (e.g. `p1.4-plugin-bridge`). No direct commits to `main`.
- **Small PRs.** One PR = one reviewable step, ideally under ~400 changed lines.
- **Every PR description follows the template** (`.github/pull_request_template.md`), including the learning notes:
  the architecture and logic of the change.
- **Verification before review:** lint, type checks and tests pass locally; game behavior is checked against the
  local server when relevant. Anything not verified is labeled "not verified".
- **Unfinished work** is written to [`backlog.md`](backlog.md) at the end of a session.

### Status legend

`todo` · `in progress` · `in review` · `done (#PR)` · `dropped (reason)`

---

## Week 1 (Oct 16 – Oct 22): foundations and the bridge

| ID | Work item | Status |
|---|---|---|
| P1.1 | Python core skeleton | in review (#29, #30) |
| P1.2 | Local server and hello bot (first TypeScript) | in review |
| P1.3 | Plugin bridge: core ↔ plugin | in review |

### P1.1 Python core skeleton
- **Goal:** a Python package Fatih set up himself, with tests running.
- **Deliverables:** `core/` with `uv`, `ruff`, `pytest` pyright strict; a guard test that keeps game names out of the core; a first small module with tests; CI running lint + tests.
- **Acceptance:** `uv run pytest` and `uv run ruff check` pass locally and in CI.
- **Learning focus:** Python modules and packages, virtual environments with `uv`, writing a first test, what CI is.

### P1.2 Local server and hello bot (first TypeScript)
- **Goal:** a reproducible local server and a bot that joins it.
- **Deliverables:** `docker-compose.yml` (itzg/minecraft-server, Java 1.21.11, offline mode, fixed seed, RCON on, bot not op); `plugins/minecraft/` TypeScript package; a Mineflayer bot that joins, says hello and answers one chat message.
- **Acceptance:** `docker compose up` + one command → the bot spawns and replies in chat.
- **Learning focus:** Docker Compose, TypeScript basics (types, `async/await`, events), how Mineflayer connects like a player.

### P1.3 Plugin bridge: core ↔ plugin
- **Goal:** the Python core starts the plugin as a child process and controls the bot through it.
- **Deliverables:** newline-delimited JSON-RPC over stdio; methods `handshake`, `observe`, `act` (move, chat) and an `events` stream; a Python client and a TS server.
- **Acceptance:** a Python script starts the plugin, completes the handshake, prints an observation (position, health, inventory) and moves the bot.
- **Learning focus:** processes and stdio, JSON-RPC, `asyncio` in Python, why the core never imports game code.

---

## Week 2 (Oct 23 – Oct 29): the learning loop

| ID | Work item | Status |
|---|---|---|
| P2.1 | Telemetry and LLM client | in review (#34) |
| P2.2 | Predicates and RCON scenarios | in review |
| P2.2a | Review round 1 fixes ([review](reviews/2026-10-16-sonnet-round-1.md)) | in review (#36) |
| P2.2b | Contract step: observation, world reset, run records | in review (#37, #38) |
| P2.3 | Skill execution in the plugin | todo |
| P2.4 | The Voyager loop + skill library | todo |

### P2.1 Telemetry and LLM client
- **Deliverables:** an `LlmClient` (Anthropic: Sonnet 5.5 for code, Haiku 5.5 for text) with timeout and error messages; every call logged as JSONL (model, tokens, cost, latency, trace id); keys only from `.env`.
- **Acceptance:** a unit test with a fake client; one live call logged with tokens and cost.
- **Learning focus:** HTTP APIs and SDKs, secrets in `.env`, structured logging, why measurement starts on day one.

### P2.2 Predicates and RCON scenarios
- **Deliverables:** predicates over observations (`has_item(name, n)`, `near(pos, r)`, …) returning `true / false / unknown`; an RCON helper that sets up a scenario (`/give`, `/tp`, `/clear`) and resets it.
- **Acceptance:** predicates give no false success on prepared negative states; a scenario can be reset and rerun.
- **Learning focus:** why verification is independent of the code being verified, test fixtures, determinism.

### P2.2b Contract step (added 2026-10-16 after review round 1)
- **Goal:** fix the contract before LLM-written code runs, so P2.3–P4.2 build on the right shape.
- **Deliverables:** richer observation (nearby blocks and entities, equipment, fair/full visibility, tick); handshake
  lists real methods and primitive schemas; `interrupt`; scenario setup with `fill` / `place` / `summon`, reset to a
  spawn point; a fresh world per seed restored from a pristine copy (`scenario.world`); a task-run record with
  `world_instance_id` and per-trace LLM totals in the core.
- **Acceptance:** a fresh world is restored per run; an observation names nearby logs; a run record links a task to
  its seed, world, verdict, time and LLM cost.

### P2.3 Skill execution in the plugin
- **Deliverables:** `runSkill(code, args)` runs JavaScript skill code in a child process with a timeout and a deny-list; a few hand-written primitives the skills may call (`goTo`, `mineBlock`, `craft`, `collect`).
- **Acceptance:** a hand-written "collect 3 logs" skill runs; an infinite loop is killed by the timeout and the bot stays alive.
- **Learning focus:** why running LLM-written code is dangerous, child processes, timeouts.

### P2.4 The Voyager loop + skill library
- **Deliverables:** task → predicate → prompt → code → run → verify → retry with the error (≤ 3); passing skills stored with a description; retrieval by keywords in later prompts.
- **Acceptance:** "craft a wooden pickaxe" is solved from an empty inventory, and the saved skill is reused in a second task.
- **Learning focus:** prompt design, feedback loops, why the predicate is written before the code.

---

## Week 3 (Oct 30 – Nov 5): reflexes, commands, memory

| ID | Work item | Status |
|---|---|---|
| P3.1 | L0 reflexes | todo |
| P3.2 | Commands, autonomy flag, persona | todo |
| P3.3 | Places memory | todo |
| P3.4 | L1: one Jev decision point | todo |

### P3.1 L0 reflexes
- **Deliverables:** event-driven reflexes in the plugin (flee or fight a nearby hostile; eat when hungry) that interrupt the current skill and report it to the core.
- **Acceptance:** a summoned zombie triggers the reflex during a running task; reaction time is logged.
- **Learning focus:** events vs polling, interrupting work safely.

### P3.2 Commands, autonomy flag, persona
- **Deliverables:** `#goto`, `#mine`, `#follow`, `#stop` parser; free text goes to L2; `full` / `consult` flag where `consult` asks with a timeout and a default; a persona prompt for chat replies.
- **Acceptance:** each command works from in-game chat; in `full` the bot never asks; in `consult` an unanswered question times out safely.
- **Learning focus:** parsing, timeouts, "a timeout never grants permission".

### P3.3 Places memory
- **Deliverables:** named places stored per world (`home`, `mine`, …) with `#sethome` and `#goto home`.
- **Acceptance:** places survive a restart of the core.
- **Learning focus:** persistence, why location questions are code, not RAG.

### P3.4 L1: one Jev decision point
- **Deliverables:** command text → skill choice with Jev (TypeSafe), with a rule fallback; every call logged.
- **Acceptance:** 10 example commands are routed; the log shows provider, confidence and latency.
- **Learning focus:** classification with probabilities, why confidence is not permission.

---

## Week 4 (Nov 6 – Nov 12): record a skill and evaluation

| ID | Work item | Status |
|---|---|---|
| P4.1 | Record a skill v1 | todo |
| P4.2 | Evaluation runner and 20+ tests | todo |

### P4.1 Record a skill v1
- **Deliverables:** `#record start/stop`; the bot logs the player's block and inventory events plus `//` chat notes; L2 turns the recording into a skill + predicate; the skill is replayed in a fresh spot and verified.
- **Acceptance:** a demonstrated small build (e.g. a 3×3 platform) is replayed and verified at least 3 out of 5 times.
- **Learning focus:** turning raw events into meaning, generalizing from one example.

### P4.2 Evaluation runner and 20+ tests
- **Deliverables:** ≥ 20 scenario tests (JSON); a runner that sets up each scenario by RCON, runs the task, applies the predicate and writes results; two arms: empty library vs learned library.
- **Acceptance:** one command runs all tests and writes a results file with success, cost and latency per test (seed, model and visibility mode recorded).
- **Learning focus:** experiment design, fixed seeds, frozen test sets.

---

## Week 5 (Nov 13 – Nov 19): report and demo

| ID | Work item | Status |
|---|---|---|
| P5.1 | Evaluation report | todo |
| P5.2 | Demo and delivery package | todo |

### P5.1 Evaluation report
- **Deliverables:** `docs/eval/report.md`: success rate (with a simple confidence interval), cost, latency, with vs without the library, failure examples, prompt-design and model-choice rationale.
- **Acceptance:** every number links to a raw result file.

### P5.2 Demo and delivery package
- **Deliverables:** README with setup and usage; CLI + a small web page showing the bot's state and log; a 3–5 minute video; a short presentation.
- **Acceptance:** all five course deliverables are ready.

---

## Later (after the prototype, in priority order)

Full designs are in `research.md`.

| ID | Work item |
|---|---|
| L1 | Hardened executor (primitive broker, resource limits, `tsc`-checked TypeScript skills) |
| L2 | Full action arbiter and measured L0 latency targets |
| L3 | Skill lifecycle, candidate versions, embedding retrieval |
| L4 | Structured memory: chests, resource state, episodic RAG |
| L5 | Task IR, behavior trees, AFK pipelines, `approver` mode |
| L6 | Record a skill v2 (recording proxy, behavioral skills, voice narration) |
| L7 | Voice commands, personality mood/diary |
| L8 | L1 question registry + shadow mode; L3 fine-tuning on `fatih-pc` |
| L9 | Full evaluation protocol (pre-registration, paired runs, McNemar/bootstrap) |
| L10 | Doom plugin; multi-agent |
