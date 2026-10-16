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

### [P2.3] Contract decisions before skill execution (review round 1)
- **Status**: blocked
- **Opened by**: claude-code · **Date**: 2026-10-16
- **Done so far**: 19 review findings fixed in #36; the open design items are listed in [docs/reviews/2026-10-16-sonnet-round-1.md](reviews/2026-10-16-sonnet-round-1.md#open-not-fixed-in-36).
- **Remaining**: decide (Fatih) whether to add a P2.2b contract step: primitive broker over IPC, asynchronous `runSkill` with cancel, richer observation (nearby blocks/entities, visibility), predicate extensions, task-run records and world reset; and whether to adopt the plan cuts suggested there.
- **Where I was**: `docs/reviews/2026-10-16-sonnet-round-1.md`
- **Blocker / unknowns**: Fatih's decision on the plan changes.
- **Branch / PR**: #36


---

## Closed

- **2026-10-16 · claude-code**: [P2.1] Live LLM calls verified: Haiku 5.5 (32/78 tokens, $0.0000422, 1590 ms) and Sonnet 5.5 with server-side fallback (28/51 tokens, $0.000566, 1356 ms), both logged to telemetry (PR #34).
- **2026-10-15 · claude-code**: Fatih revised decision 24: Claude writes the code, Fatih owns the architecture and reviews. PRs #29/#30 reopened for P1.1.
- **2026-10-15 · claude-code**: Closed the agent-written P1.1 PRs (#29, #30); Fatih will write the prototype himself. `plan.md` rewritten as the narrowed prototype plan.
- **2026-10-15 · claude-code**: Switched the repository to English and public; replaced GitHub issues with `docs/plan.md`; rewrote the README.
- **2026-10-15 · claude-code**: Research and documentation skeleton: `docs/research.md`, `AGENTS.md` (+ `CLAUDE.md` symlink), `docs/notes.md`, `docs/backlog.md`.
