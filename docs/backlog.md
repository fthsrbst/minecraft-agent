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
