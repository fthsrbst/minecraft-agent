# Backlog: unfinished work

Agents write every **unfinished** piece of work here at the end of a session; the next agent starts from here.
Planned work that has not started belongs in [`plan.md`](plan.md), not here.

## Rules

- One item per piece of work. The newest item goes to the top of **Open**.
- Never delete a finished item: move it to **Closed** with the closing date and evidence (PR, test output).
- If an item grows (sub-tasks, detailed notes, a multi-step plan), open a **sub-backlog** file `docs/backlog/<topic>.md`
  and link it from the item. Sub-backlogs use the same format and can nest further: `docs/backlog/<topic>/<sub-topic>.md`.
- When leaving work unfinished, say exactly where you were: which file, which step, what is not verified.

## Item format

```markdown
### [P1.4] Short title
- **Status**: partial | blocked | in review
- **Opened by**: <agent or Fatih> · **Date**: YYYY-MM-DD
- **Done so far**: ...
- **Remaining**: ...
- **Where I was**: file/function, last command run
- **Blocker / unknowns**: (if any)
- **Branch / PR**: (if any)
- **Sub-backlog**: [docs/backlog/<topic>.md](backlog/<topic>.md) (if any)
```

The `[P1.4]` tag is the work-item ID in `plan.md`.

---

## Open

### [P4.1] Record a skill v1: finish review round 5 fixes, live-verify, open PRs
- **Status**: partial
- **Opened by**: claude-code · **Date**: 2026-10-16
- **Where the work is**: git worktree `/Users/fatih/minecraft-agent-p41` (outside the main checkout, so the running
  evaluation is not disturbed). Branches, stacked: `p4.1-record-plugin` (on `p3.5-round4-fixes` / PR #47) →
  `p4.1-record-core`. Both pushed; **no PRs opened yet**.
- **Done so far**:
  - Plugin (`p4.1-record-plugin`, commits 184671c + 4f66a84): `src/recording/` — `frame.ts` (anchor + cardinal facing,
    relative cells a/b/c), `recorder.ts` (watches `blockUpdate` within reach of the player, `//` notes, ignores the
    bot's own work, unknown old blocks and changes > 16 from the start; auto-ends at 10 min with a `record.ended`
    event and keeps the data), `blueprint.ts` (net change → blueprint, detours dropped, `unsupported` vs `warnings`,
    deterministic JS skill code with a second placement pass), `check.ts` (structure check counts placed blocks
    only; strict parsing of the core's input). Methods `record.start/stop/check`; capability `record`;
    `scenario.arena` (force-loads chunks, fills a 17×17 stone floor + air, tp with yaw, give; facing cycles by index;
    "not loaded" counts as a failure and is retried); `#record` command; `src/tools/teacher.ts` scripted demonstrator.
    160 plugin tests pass, lint/typecheck/prettier clean.
  - Core (`p4.1-record-core`, commit "Turn a recording into a verified skill in the core" + an uncommitted-then-WIP
    commit): `recording/skill.py` (L2 intent card via Haiku, notes fenced and escaped, plain fallback card,
    `RecordedSkill` save/load, `library_description()` with materials/args/rules), `recording/verify.py` (replays in
    arenas, `record.check`, a PluginError per replay → UNKNOWN, `free_name` never overwrites a non-demonstrated
    skill, saves at ≥ 60 %), `record_demo.py` CLI, `#record start|stop <name>` in `agent.py` (typed only; L1 never).
    236 core tests pass, pyright/ruff clean.
- **Remaining** (review round 5 findings, Sonnet, 2026-10-16; not yet written to `docs/reviews/`):
  1. `agent.py` `_record` stop branch: call `save_raw(self.recordings_dir, stopped)` **before** `build_skill`
     (save_raw is not written yet: add it to `recording/skill.py`), report "kept as raw, no skill" on RecordingError;
     say `Note: …` for `skill.warnings`.
  2. `agent.py`: add `_recording_ended` + `recording_ended(player, reason)`; `serve()` handles the `record.ended`
     event; `#record start` is allowed again once a recording ended on its own.
  3. `record_demo.py`: print `result.name` when saved.
  4. Tests: agent stale-recording path, raw kept when nothing was built, `free_name` collision, a replay that raises
     PluginError → UNKNOWN, `library_description` content.
  5. Write `docs/reviews/2026-10-16-sonnet-round-5.md` (findings 1–18 and what was fixed). Not fixed by design:
     any player may record (localhost; document as a decision), attribution is still "near the player" (v2 proxy).
  6. **Live verification** (needs the server; wait until the evaluation run below has finished):
     agent `--autonomy full` as AgentBot; RCON: give Teacher 9 oak_planks and put both on flat ground a few blocks
     apart; `node plugins/minecraft/dist/tools/teacher.js`; then
     `uv run --env-file ../.env python -m agent_core.record_demo ../plugins/minecraft runs/recordings/<id>.json --runs 5`.
     Acceptance (plan P4.1): verified ≥ 3/5. Watch RCON replies for "not loaded".
  7. Open two PRs (plugin on #47's branch, core on the plugin branch), plan status P4.1 → in review.
- **Blocker / unknowns**: v1 cannot see inventory/crafting (watcher bot, not the proxy); block states and overhangs
  are not supported (reported as unsupported/warnings).

### [P4.2] Full plan-v1 evaluation: first run is not valid (infrastructure failures)
- **Status**: blocked (needs an infrastructure fix, then a rerun)
- **Opened by**: claude-code · **Date**: 2026-10-17
- **Done so far**: full run finished 2026-10-17 ~16:10 (`core/runs/eval/plan-v1-full`, report via
  `uv run python -m agent_core.evaluation report runs/eval/plan-v1-full`). Learning 24/44; test no-library 19/66 (29%),
  frozen-library 21/66 (32%), McNemar p = 0.75. **Do not report these numbers**: the failures are mostly the
  server, not the agent. Failure reasons:
  - `scenario.world`: "minecraft-agent-server was not healthy within …" (20 runs);
  - bot disconnected with `keepAliveError` (17);
  - handshake "No spawn within 60000 ms" (6);
  - "a reflex kept the bot busy; the skill could not start" (6);
  - 59 test runs "out of attempts", many with a wall time of about 15 s, which is too fast for real attempts.
    Check whether those attempts failed on a dead bot.
  The pilot (3 tasks, `runs/eval/pilot-1`) did not show these problems: the server degrades over a long run.
- **Remaining**:
  1. Investigate server health over many world switches: Docker/Colima memory and CPU, server logs
     (`docker logs minecraft-agent-server`), the health-check timeout in `plugins/minecraft/src/scenario/world.ts`,
     keepAlive timeouts (a long GC pause or an overloaded host).
  2. The runner should mark infrastructure failures as **broken**, not as a FALSE verdict, and retry them. This
     covers runs where the bot is disconnected, there is no spawn, or the world switch fails. Then a resume reruns
     them: `runner.py` / `execute.py`.
  3. Attempts that fail because the bot is gone must not use up attempts (`voyager/loop.py`).
  4. Rerun (the runner resumes; delete or move `runs/eval/plan-v1-full` first for a clean run), write the report,
     add it to PR #46 and `docs/notes.md`.

### [P3.2] Validate command arguments against the game before "On it"
- **Status**: partial
- **Opened by**: claude-code · **Date**: 2026-10-16
- **Done so far**: numbers, positions, names and lengths are validated in the core parser (round 4).
- **Remaining**: `#follow nobody` and `#mine notablock` say "On it" and fail seconds later. Add a generic, optional
  plugin capability (e.g. `vocabulary.check {kind, value}` for block kinds and visible players) and call it before
  starting work; the core stays game-independent.
- **Where I was**: `core/src/agent_core/agent.py` `_run_command`; review round 4 live QA #11.

### [P2.2] Scenario reset leaves natural mobs behind
- **Status**: partial
- **Opened by**: claude-code · **Date**: 2026-10-16
- **Done so far**: reset kills tagged (scenario) mobs; evaluation runs use fresh seeded worlds, which avoids the problem.
- **Remaining**: in a reused world, night spawns near the bot make reflex runs noisy. Option: reset also sets
  `time day` and removes hostile mobs within a radius of the bot.
- **Where I was**: `plugins/minecraft/src/scenario/commands.ts` reset; review round 4 live QA #12.

---

## Closed

- **2026-10-16 · claude-code**: [P2.3] Contract decisions from review round 1 implemented on Fatih's decision: P2.2b (#37, #38), P2.3 (#39), review round 2 fixes (#40, `docs/reviews/2026-10-16-sonnet-round-2.md`). Plan cuts remain a proposal.
- **2026-10-16 · claude-code**: [P2.1] Live LLM calls verified: Haiku 5.5 (32/78 tokens, $0.0000422, 1590 ms) and Sonnet 5.5 with server-side fallback (28/51 tokens, $0.000566, 1356 ms), both logged to telemetry (PR #34).
- **2026-10-15 · claude-code**: Fatih revised decision 24: Claude writes the code, Fatih owns the architecture and reviews. PRs #29/#30 reopened for P1.1.
- **2026-10-15 · claude-code**: Closed the agent-written P1.1 PRs (#29, #30); Fatih will write the prototype himself. `plan.md` rewritten as the narrowed prototype plan.
- **2026-10-15 · claude-code**: Switched the repository to English and public; replaced GitHub issues with `docs/plan.md`; rewrote the README.
- **2026-10-15 · claude-code**: Research and documentation skeleton: `docs/research.md`, `AGENTS.md` (+ `CLAUDE.md` symlink), `docs/notes.md`, `docs/backlog.md`.
