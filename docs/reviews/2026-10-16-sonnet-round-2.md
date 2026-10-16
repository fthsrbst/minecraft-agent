# Review round 2 (2026-10-16): Sonnet 5.5 agents on PRs #37–#39

Two independent Claude Sonnet 5.5 agents reviewed the P2.2b contract step and P2.3 skill execution:

- **Code and security review** (read-only, offline experiments that fork the real executor).
- **Live QA** against the local server (own worktree, bot `QABot`, world switches allowed): adversarial skills,
  primitive abuse, world restore, observation, and success rates of the hand-written skills.

Fixes are in PR #40 (`p2.3b-hardening`). Round 1 is in [`2026-10-16-sonnet-round-1.md`](2026-10-16-sonnet-round-1.md).

## Sandbox verdict

**No escape found by either agent.** Tried and refused:

- **Language-level routes:** `process`, `require`, `import()`, `eval`, `Function` and the main-realm `Function`
  constructor via `bot.chat`, `log`, `args`, Promises and prototypes (all blocked by "code generation from strings
  disallowed"), WebAssembly, and `Error.prepareStackTrace` frame walking.
- **Host access:** file reads and writes, child processes, and network connections to the RCON and game ports.
- **Abusing the bot API:** chat commands, including after a newline.

One message-forgery route existed (a main-realm `Object.prototype.toJSON`). It gave no extra capability, and it is
closed now.

## Fixed in #40

| # | Source | Finding | Fix |
|---|---|---|---|
| 1 | QA | `craft` returned before the inventory updated: the next craft failed, once an oak button was crafted instead of sticks; wooden pickaxe passed **2/5** | Crafts wait for a quiet inventory before and after, verify the item appeared, retry once on Mineflayer's "updateSlot did not fire" |
| 2 | QA | `collect` failed as a whole when one block was unreachable or its path took too long to plan; reported success with nothing gained | One block at a time, nearest first, unreachable ones skipped; `complete`/`mined` reported; fails only when nothing was mined; refuses air/water/lava |
| 3 | Review | Fair mode was not fair: `collect` searched 64 blocks regardless of sight (an x-ray oracle) | `collect` uses the same visibility rule as `observe` (in sight, within 32) |
| 4 | Review + QA | Fair-mode observation showed ore lining sealed caves and mobs behind walls; entities ignored `radius` | One flood fill of the open space connected to the bot's eyes; visible = its solid boundary; entities only inside it and within `radius` |
| 5 | QA | Observation silently cut at 50,000 blocks (≈ 22-block radius underground) | Fair mode reads the boundary directly; full mode asks for the whole sphere; `nearbyTruncated` when a budget is hit |
| 6 | QA | Chat with `§` or spam (≈ 10 quick lines) got the bot kicked | `§` and invisible characters refused; 1.5 s between lines; 20 lines per skill |
| 7 | QA | A kick or world switch during a skill did not stop it | Skill cancelled on `disconnected` and `death` |
| 8 | Review | Orphaned executor at 100% CPU when the plugin died | `disconnect` exits the executor; a CPU-time limit (`ulimit -t`) ends busy loops |
| 9 | Review | `--max-old-space-size` did not cap memory (6 GiB of typed arrays allocated) | Resident memory polled every 500 ms, killed above 512 MB |
| 10 | Review | Calls queued before a cancel still ran; `craft`/`equip` started before the abort check; a new skill could start while the old one's primitive ran | Queued calls skipped after cancel; abort checked before any game action; new skills wait until the previous run has settled |
| 11 | Review + QA | Log flood (2,567 messages, SIGABRT), unbounded result; a 50 MB result killed the plugin through the core's line limit | 100 log lines, 500 chars each; results over 20,000 characters refused |
| 12 | Review | Main-realm prototypes reachable from skill code allowed rewriting outgoing messages (`toJSON`) | Executor freezes `Object`, `Array`, `Function`, `Promise`, `Error`, … before running code |
| 13 | QA + Review | `throw undefined` / `throw Symbol()` and unawaited rejected primitives crashed the executor | Every thrown value is described; unhandled rejections are logged and the run continues |
| 14 | QA | `endless-loop.js` ended as `error` (vm 5 s limit) instead of `timeout` | No vm limit; the broker deadline gives `timeout` |
| 15 | Review | Two demos could record a false success (predicate already true before the run) | Success only when the predicate was `false` before; otherwise `unknown` with the reason |
| 16 | Review | Runs that raised wrote no record (survivorship bias) | Broken runs are recorded with verdict `unknown` and the error |
| 17 | Review | `run_skill` leaked its event waiter; a lost `skill.run` reply left an orphan run | Waiter always forgotten; cancel without id when the run id is unknown |
| 18 | Review | `summarize_trace` crashed on a cut-off line; a missing file looked like "no LLM calls"; cache tokens not summed | Bad lines skipped and counted (total marked incomplete); `telemetry_found`; cache tokens summed |
| 19 | Review | An interrupted first world generation left a half "pristine" copy used forever | Copy to `.partial`, require `level.dat`, then rename |
| 20 | QA | `place` found no spot next to trees | 4-block search, more plants replaceable, result verified |
| 21 | QA | Invalid seed → internal error; `goTo` failures said only "Path was stopped" | Invalid params error; "no path to (x, y, z): …"; pathfinder planning time 10 s |

## Measured after the fixes (local server)

| Check | Before (QA) | After |
|---|---|---|
| `wooden-pickaxe.js` from nothing, fresh world each run | 2/5 (40 %) | **8/8** (seeds 20261119 ×5, 12345 ×3), 18–91 s, 7 primitive calls |
| `endless-loop.js`, 3 s timeout | status `error` after 5 s | status `timeout` at 3.0 s, bot alive, no executor left |
| 50 MB skill result | plugin killed | `error: result is larger than 20000 characters`, plugin alive |
| `bot.chat("hello §kfoo")` | bot kicked | refused before sending |
| Fair `observe`, radius 16 / 32 | 130 / 366 ms (p50) | 27 / 225 ms (p50), not truncated |

## Open

- Node 22's permission model does not restrict the network; the executor has no credentials and only reaches localhost
  ports. Network isolation stays in "Later" (L1).
- `scenario.world` restarts the server under a connected bot; runs must switch worlds between attempts (the runner
  does). Seeds are limited to ±2^53 (Minecraft allows 64-bit).
- Telemetry has no per-trace index (`summarize_trace` reads the file); fine at the expected size.
- Primitives run one at a time by design: a long `goTo` blocks later calls of the same skill until it ends.
