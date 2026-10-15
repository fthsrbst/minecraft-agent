# Implementation Plan

> Delivery: **2026-11-19** (5 weeks from 2026-10-15). This document replaces GitHub issues as the work tracker.
> Design and rationale: [`research.md`](research.md). Decisions and rules: [`AGENTS.md`](../AGENTS.md).

## How we work

- **Claude writes the code; Fatih reviews it and learns from it.** Every code change goes through a pull request; nothing is merged without Fatih's approval.
- **This plan is the tracker.** Each work item has an ID (`P1.3`), a goal, deliverables, an acceptance criterion and the PRs it will produce. The status column is updated in the same PR that changes it.
- **Branches:** `p<week>.<item>-<short-name>` (e.g. `p1.4-plugin-protocol`). No direct commits to `main`.
- **Small PRs.** One PR = one reviewable step, ideally under ~400 changed lines and readable in about 30 minutes. A work item can have several PRs.
- **Every PR description follows the template** (`.github/pull_request_template.md`): what changed, why, how it was verified (commands + output), **learning notes** (concepts, why this approach, where to start reading) and where to look closely.
- **Verification before review:** lint, type checks and tests pass locally; game behavior is checked against the local server when relevant. Anything not verified is labeled "not verified".
- **Review loop:** Fatih comments or asks questions on the PR; Claude answers and pushes fixes to the same branch. Squash merge after approval. Commit subjects are imperative, ≤ 72 characters.
- **Spikes** produce a short report in `docs/spikes/S<n>.md` with the hypothesis, setup, raw numbers and a decision (continue / change / drop). The success criterion is fixed before the spike runs.
- **Unfinished work** is written to [`backlog.md`](backlog.md) at the end of a session.

### Review guide (for Fatih)

1. Read the PR's **learning notes** first; they tell you what to look at and in which order.
2. Run the "How it was verified" commands yourself when you can; seeing it work is the fastest way to understand it.
3. Ask about anything unclear, even small things. A question is a valid review comment.
4. Check that the change matches the work item's acceptance criterion in this plan.
5. Approve when you understand it and it does what the plan says.

### Status legend

`todo` · `in progress` · `in review` · `done (#PR)` · `dropped (reason)`

---

## Week 1 (Oct 16 – Oct 22): the bot is up and safe

| ID | Work item | Status |
|---|---|---|
| P1.1 | Repository skeleton and CI | todo |
| P1.2 | Local Minecraft server and first bot | todo |
| P1.3 | Spike S1: version compatibility | todo |
| P1.4 | Plugin protocol v0 | todo |
| P1.5 | Spike S2 + isolated skill executor | todo |
| P1.6 | Action arbiter, cancellable primitives, L0 safety | todo |
| P1.7 | Spike S3 + predicates, RCON scenarios, reset | todo |

### P1.1 Repository skeleton and CI
- **Goal:** both codebases exist, build, lint and test automatically.
- **Deliverables:** `core/` Python 3.13 package (uv, ruff, pyright strict, pytest); `plugins/minecraft/` TypeScript package (npm, tsc strict, eslint, prettier, vitest); GitHub Actions running lint + types + tests for both; README setup section.
- **Acceptance:** a fresh clone passes `uv run pytest`, `uv run pyright`, `npm test`, `npm run typecheck`; CI is green.
- **PRs:** (1) Python core skeleton + CI; (2) TypeScript plugin skeleton + CI.
- **Learning focus:** `pyproject.toml` and uv, why strict type checking, how a CI workflow is structured.

### P1.2 Local Minecraft server and first bot
- **Goal:** a reproducible local server and a bot that joins it.
- **Deliverables:** `docker-compose.yml` (itzg/minecraft-server, Java 1.21.11, offline mode, fixed seed, RCON on, `enforce-secure-profile=false`, bot not op); scripts to start/stop/reset; a minimal Mineflayer bot that joins and chats; prismarine-viewer in the browser.
- **Acceptance:** `docker compose up` + one command → the bot spawns and is visible in the viewer.
- **PRs:** (1) server compose + scripts; (2) hello-bot + viewer.
- **Learning focus:** Docker Compose, RCON, how Mineflayer connects like a player.

### P1.3 Spike S1: version compatibility
- **Hypothesis / experiment / criterion:** research.md §14.6 S1. Compare with Mindcraft's versions and `patches/`.
- **Deliverables:** `docs/spikes/S1.md`; pinned versions in `package.json`; any borrowed patch recorded with source and version.
- **Acceptance:** 10/10 runs of walk → chop → craft table and pickaxe → kill a zombie → use a chest, or a written decision on which package needs a fork/patch.
- **PRs:** (1) spike script + report + pins.
- **Learning focus:** dependency pinning, reading a library's issue tracker, how to time-box an experiment.

### P1.4 Plugin protocol v0
- **Goal:** the Python core talks to the TypeScript plugin as a separate process.
- **Deliverables:** versioned JSON-RPC over stdio with `handshake`, `observe`, `act`, `reset`, `events` (with sequence numbers); one schema definition validated on both sides; a Python client and a TS server; a conformance test.
- **Acceptance:** the core starts the plugin, completes the handshake, reads an observation, moves the bot with `act`, and receives ordered events; conformance tests pass.
- **PRs:** (1) schemas + conformance tests; (2) TS server; (3) Python client.
- **Learning focus:** process boundaries, JSON-RPC, schema-first design, why the core never imports game code.

### P1.5 Spike S2 + isolated skill executor
- **Hypothesis / experiment / criterion:** research.md §14.6 S2.
- **Deliverables:** `docs/spikes/S2.md`; an executor process for skill code (no keys, restricted fs/net, CPU/memory limits); a permission-checked primitive broker; an external watchdog; static checks (no loop without `await`, no `bot.chat('/…')`, no `require`/`process`); `tsc` check for skill code; `runSkill` and `interrupt` in the protocol.
- **Acceptance:** all 20 faulty skills are killed within 2 s with the main process alive; after an interrupt acknowledgement stale work cannot send actions.
- **PRs:** (1) spike + report; (2) executor + broker + watchdog; (3) static checks + `tsc` gate.
- **Learning focus:** why `vm` is not a sandbox, event loops, watchdogs, defense in depth.

### P1.6 Action arbiter, cancellable primitives, L0 safety
- **Goal:** exactly one owner of the bot at any time, and fast emergency reactions.
- **Deliverables:** core arbiter (priorities: emergency safety > player command > trigger > task; resource ownership; job ids/generations; discard late results; re-check preconditions before resume); primitives wrapped with their own stop paths and interrupt acks; L0 reflexes (flee/defend on nearby hostile, low health, lava/fall).
- **Acceptance:** concurrent "go home" triggers produce one plan; a zombie approaching mid-task triggers the reflex within 100 ms of the event (measured).
- **PRs:** (1) arbiter in the core; (2) cancellable primitives in the plugin; (3) L0 reflexes + latency measurement.
- **Learning focus:** concurrency and ownership, cooperative cancellation, measuring latency correctly.

### P1.7 Spike S3 + predicates, RCON scenarios, reset
- **Hypothesis / experiment / criterion:** research.md §14.6 S3.
- **Deliverables:** `docs/spikes/S3.md`; predicate library v0 (`inventory.has`, `isNight`, `insideEnclosure`…) returning `true / false / unknown`; RCON scenario builder (`/give`, `/tp`, `/summon`, `/fill`); hard/soft reset; `world_instance_id` + `episode_id`; fair-visibility filter v0.
- **Acceptance:** zero false successes on prepared negative states; reset reproduces the defined start-state fields in 20/20 runs.
- **PRs:** (1) spike + report; (2) predicates + scenario builder + reset; (3) visibility filter.
- **Learning focus:** why the verifier must be independent, test fixtures, determinism.

---

## Week 2 (Oct 23 – Oct 29): the first learning loop

| ID | Work item | Status |
|---|---|---|
| P2.1 | Telemetry and run records | todo |
| P2.2 | LlmClient (Claude) | todo |
| P2.3 | Single-task skill-writing loop | todo |
| P2.4 | Evaluation runner and first frozen scenarios | todo |
| P2.5 | Spike S5: L2 model selection | todo |
| P2.6 | Skill library | todo |
| P2.7 | Starter core and bounded `obtain` | todo |

### P2.1 Telemetry and run records
- **Deliverables:** trace ids across L2 call → skill → primitive → event; JSONL run records (tokens, $, ms, outcome, seed, model, visibility mode); a small CLI to summarize a run.
- **Acceptance:** any run can be summarized into cost, latency and outcome per task.
- **PRs:** (1) tracing + records; (2) summary CLI.
- **Learning focus:** structured logging, why measurement is built in from day one.

### P2.2 LlmClient (Claude)
- **Deliverables:** a provider-independent `LlmClient` with Anthropic as the first provider (Sonnet 5.5 / Haiku 5.5), prompt caching, timeouts, retries, cost accounting; keys only from `.env`.
- **Acceptance:** unit tests with a fake provider; one live call recorded with tokens and cost.
- **PRs:** (1) client + fake provider + tests.
- **Learning focus:** API clients, prompt caching, keeping secrets out of code.

### P2.3 Single-task skill-writing loop
- **Deliverables:** L2 writes a TypeScript skill for a task; the acceptance predicate is written first; `tsc` + static checks; run in the executor; up to 4 attempts with error + critique feedback (Voyager's two-message format).
- **Acceptance:** "craft a wooden pickaxe" is solved from an empty inventory.
- **PRs:** (1) prompt templates + predicate-first step; (2) the attempt loop.
- **Learning focus:** prompt design, why the predicate comes before the code, feedback loops.

### P2.4 Evaluation runner and first frozen scenarios
- **Deliverables:** an evaluation runner that sets up RCON scenarios, runs tasks, applies predicates and writes results; 5 frozen scenarios in MineCollab-style JSON; a report generator (success with Wilson CI, cost, latency).
- **Acceptance:** one command runs the 5 scenarios and produces a report.
- **PRs:** (1) runner + scenario format; (2) report generator.
- **Learning focus:** experiment design, confidence intervals, frozen test sets.

### P2.5 Spike S5: L2 model selection
- **Hypothesis / experiment / criterion:** research.md §14.6 S5 (Haiku / Sonnet / Opus / cascade on a 10-task slice).
- **Deliverables:** `docs/spikes/S5.md` with the decision; default models updated in config.
- **PRs:** (1) slice + runs + report.
- **Learning focus:** comparing models fairly (paired runs, same seeds).

### P2.6 Skill library
- **Deliverables:** skill contract schema (§8.2); storage in SQLite + skill files written atomically; lifecycle draft → verified → trusted, candidate versions for repairs; scenario tests per skill; retrieval (BM25/embeddings) returning 3–5 skills in dependency order.
- **Acceptance:** a skill learned in one task is retrieved and reused in another; a repair stays a candidate until it passes regression.
- **PRs:** (1) contract + storage; (2) lifecycle + regression; (3) retrieval.
- **Learning focus:** data modeling, versioning, why candidates never overwrite working skills.

### P2.7 Starter core and bounded `obtain`
- **Deliverables:** primitives and ~20 starter skills (partly borrowed from Mindcraft, each recorded with source and version); a bounded `obtain(item, n)` solver over the recipe graph with `unsupported`/`unreachable` results.
- **Acceptance:** `obtain` reaches a stone pickaxe from an empty inventory in a fresh world; unsupported items fail cleanly.
- **PRs:** (1) primitives + borrowed skills; (2) `obtain` solver.
- **Learning focus:** graph search over recipes, reusing open-source code responsibly.

---

## Week 3 (Oct 30 – Nov 5): exploration, memory, L1

| ID | Work item | Status |
|---|---|---|
| P3.1 | Curriculum | todo |
| P3.2 | Structured memory | todo |
| P3.3 | DecisionClient and question registry | todo |
| P3.4 | Spike S4: Jev vs rule | todo |
| P3.5 | Spike S7: learning contribution | todo |

### P3.1 Curriculum
- **Deliverables:** task proposals (L2), feasibility checks via the knowledge provider, failure lessons (remedies) stored in memory.
- **Acceptance:** 60 iterations of autonomous exploration without invented tasks.
- **PRs:** (1) proposals + feasibility; (2) failure lessons.

### P3.2 Structured memory
- **Deliverables:** place records (home, portal pairs, villages, mines), chest memory, resource state with exhausted/unknown; plugin extractors; re-verification; utility calculation for "where to get X"; memory as planner tools.
- **Acceptance:** "go back to the village", "which chest has the diamonds" and "do not go to the exhausted mine" tasks pass in fair mode.
- **PRs:** (1) store + places + chests; (2) resource state + utility; (3) extractors + re-verification.
- **Learning focus:** why location questions are code, not RAG; time-bounded validity.

### P3.3 DecisionClient and question registry
- **Deliverables:** `DecisionClient` with `rules`, `typesafe` (Jev) and one local provider; versioned question definitions; thresholds per (question, provider, version, projection); shadow mode; full call logging.
- **Acceptance:** tactical and skill-rerank questions run in shadow mode with logged disagreements.
- **PRs:** (1) client + providers; (2) registry + shadow mode.
- **Learning focus:** classification with calibrated probabilities, why confidence is not permission.

### P3.4 Spike S4: Jev vs rule
- research.md §14.6 S4 → `docs/spikes/S4.md`; points that pass the value test are enabled.

### P3.5 Spike S7: learning contribution
- research.md §14.6 S7 → `docs/spikes/S7.md`; first small-scale evidence for the main claim.

---

## Week 4 (Nov 6 – Nov 12): commands, teaching, evaluation runs

| ID | Work item | Status |
|---|---|---|
| P4.1 | Commands and AFK pipelines | todo |
| P4.2 | Spike S6: recording proxy | todo |
| P4.3 | Record a skill v1 | todo |
| P4.4 | Pre-registration and main evaluation runs | todo |

### P4.1 Commands and AFK pipelines
- **Deliverables:** `#command` parser (`#mine iron 64`, `#goto home`, `#follow`, `#stop`); natural language → L2 → Task IR; behavior-tree runtime with triggers, guards, budgets, reports; persistent pipeline state and death recovery; AFK summary; autonomy level `full`.
- **Acceptance:** the research.md §9.1 example finishes unattended.
- **PRs:** (1) Task IR + runtime; (2) parser + NL compiler; (3) persistence + AFK summary.

### P4.2 Spike S6: recording proxy
- research.md §14.6 S6 → `docs/spikes/S6.md`.

### P4.3 Record a skill v1
- **Deliverables:** proxy recorder with meaning layers; blueprint extraction from the server-side block diff + `buildBlueprint`; named subgoal macro; `//` text narration; independent acceptance predicate; replay on unseen terrain.
- **Acceptance:** a demonstrated 3×3 shelter is rebuilt on unseen terrain (≥ 4/5 demonstrations replay successfully).
- **PRs:** (1) recorder + event translator; (2) blueprint + macro; (3) verification + library integration.

### P4.4 Pre-registration and main evaluation runs
- **Deliverables:** `docs/eval/preregistration.md` (task set, learning/test seeds, predicates, arms, sample sizes); parallel Docker servers on the PC; main arm runs (frozen core vs core + learned library, ≥ 20–30 paired runs).
- **Acceptance:** pre-registration merged before runs start; raw results stored.

---

## Week 5 (Nov 13 – Nov 19): report and demo

| ID | Work item | Status |
|---|---|---|
| P5.1 | Evaluation report | todo |
| P5.2 | Demo and delivery package | todo |

### P5.1 Evaluation report
- **Deliverables:** `docs/eval/report.md`: ≥ 20 tests (25-task set), success rates with CIs, cost, latency, main-claim result (McNemar / bootstrap), ordered ablations, failure taxonomy, prompt-design and model-choice rationale (S5).
- **Acceptance:** every number links to a raw result file.

### P5.2 Demo and delivery package
- **Deliverables:** README with setup and usage; a minimal web dashboard or CLI demo; a fixed "filming seed"; diary + highlight timestamps; a 3–5 minute video; a short presentation.
- **Acceptance:** all five course deliverables are ready.

---

## Extensions (in scope, in priority order, as time allows)

| ID | Work item | Status |
|---|---|---|
| E1 | `approver` / `consult` autonomy modes (timed questions, timeouts never grant permission) | todo |
| E2 | Voice commands (Whisper) + TTS read-back | todo |
| E3 | Personality: persona, bounded mood, narration (diary and highlights start in P5.2) | todo |
| E4 | Record a skill v2: behavioral skills (farming, combat) + voice narration | todo |
| E5 | Episodic RAG + lessons and decisions | todo |
| E6 | Visual pipeline editor + scheduling + notifications | todo |
| E7 | L3: S1-Bench, Unsloth fine-tuning on `fatih-pc`, counterfactual pilot | todo |
| E8 | Ender Dragon stretch target (unknown world, survival, fair mode) | todo |

## After delivery

| ID | Work item | Status |
|---|---|---|
| A1 | Doom plugin (ViZDoom, Python) + spike S8 | todo |
| A2 | Multi-agent: per-agent identities, shared/private memory, world coordinator, structured messages | todo |
