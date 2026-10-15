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

_No unfinished work yet. Coding starts with P1.1 in `plan.md`._

---

## Closed

- **2026-10-15 · claude-code**: Closed the agent-written P1.1 PRs (#29, #30); Fatih will write the prototype himself. `plan.md` rewritten as the narrowed prototype plan.
- **2026-10-15 · claude-code**: Switched the repository to English and public; replaced GitHub issues with `docs/plan.md`; rewrote the README.
- **2026-10-15 · claude-code**: Research and documentation skeleton: `docs/research.md`, `AGENTS.md` (+ `CLAUDE.md` symlink), `docs/notes.md`, `docs/backlog.md`.
