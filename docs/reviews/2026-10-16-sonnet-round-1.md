# Review round 1 (2026-10-16): Sonnet 5.5 agents on PRs #29–#35

Three independent Claude Sonnet 5.5 agents reviewed the unmerged stack (P1.1–P2.2) at commit `8f171ae`:

- **Code review** (read-only): correctness, robustness, security.
- **Design and plan critique** (read-only): contract fit for P2.3/P2.4, predicates, evaluation, schedule.
- **Live QA** against the local server (bot `QABot`, own worktree): protocol abuse, scenario abuse, predicates against real states, timing.

Fixes are in PR #36 (`p2.2b-hardening`). Items not fixed there are listed under "Open" and tracked in
[`backlog.md`](../backlog.md).

## Fixed in #36

| # | Source | Finding | Fix |
|---|---|---|---|
| 1 | QA | `act chat "hi\n/me x"` ran a server command: Mineflayer sends each line separately | Control characters (incl. newlines) are rejected |
| 2 | Code | `NaN`/`Infinity` in an observation made `not(...)` and `!=` return TRUE (false success) | Non-finite numbers are `unknown` |
| 3 | QA | An RCON auth timeout put the password into the error message | The auth body is never echoed |
| 4 | Code | Every plugin process received all secrets (API keys, RCON password) | Manifest `env` allowlist per component; base env only otherwise |
| 5 | Code | A non-UTF-8 or oversized stdout line killed the reader; requests hung until timeout; `close()` raised | Reader catches, stops the plugin, fails pending requests |
| 6 | Code | `stdin.drain()` outside the timeout: a plugin that stops reading blocked forever | Write and drain inside the timeout |
| 7 | Code | `close()` could leave other tasks' requests hanging; requests after close hung | `close()` fails pending requests; later requests fail fast |
| 8 | Code + QA | `item in itemsByName` accepted `constructor`, `toString`, … | `Object.hasOwn`; `air` rejected |
| 9 | Code + QA | Overlapping `act move` calls cut each other short but both reported `ok` | Actions run one at a time |
| 10 | Code | Negative/fractional stack counts were summed (`-5 + 6 = 1`) | Such inventories are `unknown` |
| 11 | Code | Worn armor and offhand were missing from `inventory` (`not has_item` could be TRUE) | All inventory slots are reported |
| 12 | Code | `near` ignored the dimension | Optional `dimension` on `near` |
| 13 | Code | Corrupt RCON length could loop forever; waiters were dropped on close; setup/reset could interleave | Length validated; waiters rejected; RCON calls serialized |
| 14 | Code | A late socket error after a failed join could crash the plugin; a pre-spawn disconnect waited 60 s | No-op error listener; `end` before spawn rejects |
| 15 | QA | `tp` with `1e-7` was sent in exponent form and rejected by the server mid-setup | Plain decimal formatting |
| 16 | Code | Boolean JSON-RPC ids matched request 1; unbounded event queue | Booleans rejected; queue bounded at 1000 (oldest dropped) |
| 17 | Code | Cancelled LLM calls left no telemetry; a telemetry write error masked the LLM result | `BaseException` recorded; telemetry errors logged |
| 18 | QA | After a disconnect, errors said "not spawned yet" | Message names the disconnect reason |
| 19 | Design | Observations had no ordering | `tick` (world age) in every observation |

## Open (not fixed in #36)

Design decisions that belong to P2.2b / P2.3 (see backlog):

- **Skill execution needs a primitive broker now**, not "Later": the skill child process cannot reach the bot, so
  primitives must be IPC calls validated and executed by the parent (design #1).
- **`runSkill` must be asynchronous** (`runId`, `skill.cancel`, terminal `skill.done` event); `interrupt` for `act`
  (design #2).
- **Thin observation**: no nearby blocks/entities, no visibility mode; the LLM cannot find a tree (design #3).
- **Predicate gaps**: block state (`block_at`, `count_blocks`), equipment, inventory delta from a baseline, entities;
  validate `compare.path` against a declared observation schema; "predicate lint" (false at start) (design #4).
- **Evaluation integrity**: reset does not restore blocks, position or world; single seed; no task-run record,
  `world_instance_id` or library snapshot id (design #5, QA #4).
- **Scenario setup is not atomic**: a server-side rejection after earlier commands leaves a half-applied state;
  failure detection relies on English reply texts (code #8, QA #3).
- Smaller: SDK retries are invisible in telemetry; fallback usage across several models is priced at the serving
  model; `.env.example` ships `change-me` as RCON password; handshake does not list primitive schemas.

## Plan suggestions from the design critique (for Fatih to decide)

- Add a short **P2.2b** before P2.3 for the contract changes above.
- Build a **minimal evaluation runner right after P2.4** (3 tasks) so reset and leakage problems surface in week 3.
- Simplify or cut: `#follow`, the L1 Jev point (keep the rule fallback), persona, and narrow record-a-skill to one
  hard-coded demonstration as a stretch goal.
- Write the 20+ task list (predicates + setups) during week 2.

## Measured by QA (local server, 2026-10-16)

Handshake 0.47–0.49 s (cold) · `observe` p50 0.11 ms, p95 0.18 ms · 50 parallel observes in 2 ms ·
`scenario.setup` mean 6.7 ms · `scenario.reset` mean 8.2 ms · walking ≈ 3.2–3.8 blocks/s · death event ≈ 5.5 s after a
fall from y=320, auto-respawn works.
