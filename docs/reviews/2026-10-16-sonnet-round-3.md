# Review round 3 (2026-10-16): Sonnet 5.5 agents on PR #41 (Voyager loop)

Two independent Claude Sonnet 5.5 agents reviewed the Voyager loop and skill library:

- **Code and prompt review** (read-only, offline experiments with fakes).
- **Live QA** (own worktree, bot `QABot`, $3 LLM budget, $0.58 spent): learning and reuse across seeds 12345 and 777,
  frozen arms, new tasks (dirt, chest, torches, stand on a table, a task without a predicate), prompt injection in the
  goal and in chat, impossible and timed-out tasks.

Fixes are in PR #42 (`p2.4b-hardening`), plus two follow-ups in #45 (final observation in records, longer library
code in prompts). Rounds 1–2: [`round-1`](2026-10-16-sonnet-round-1.md), [`round-2`](2026-10-16-sonnet-round-2.md).

## Fixed

| # | Source | Finding | Fix |
|---|---|---|---|
| 1 | Review + QA | A skill that reached the goal but then threw was stored as verified (QA saw it live: `placeCraftingTableAndStandOnIt`) | Stored and counted only when the predicate holds **and** the skill ended `ok`; otherwise the problem says "the goal holds, but the skill ended with …" |
| 2 | Review | A draft reusing a library name stored a v2 that calls itself (infinite recursion) | Taken names, API names and self-calls are refused before running |
| 3 | Review | Attempts 2–3 started from attempt 1's leftovers | Every retry starts from a reset; `clean_start` per attempt |
| 4 | Review | One LLM refusal or plugin error ended the whole batch and lost the attempts | Per-attempt handling; a broken task is recorded and the batch continues |
| 5 | Review | Library could produce SyntaxErrors: reserved words as names, calls detected in comments/strings/`bot.x(` | Reserved words refused; calls detected in code only; colliding declarations refused; `skill.check` compiles before any game time |
| 6 | Review + QA | LLM-written predicates were not recorded; no final observation | Records keep the predicate, its author, the prompt version, both library snapshots, the final observation and each attempt's code |
| 7 | Review | `parse_skill`: `</code>` in a string cut the code; several blocks taken silently; cut-off answers | Exactly one name/description; code to the last `</code>`; truncated answers refused |
| 8 | Review | Untrusted text (goal, observations, library code, errors) entered the prompt unfenced | `<data>` sections with our tags escaped; the system prompt says data never changes the rules |
| 9 | Review | Frozen library could still write; no baseline arm | SQLite read-only mode; `--no-library` arm |
| 10 | QA | Library code shown cut at 1,500 characters (skills are ~3 KB) | 6,000 characters, with an explicit cut marker |
| 11 | Review | Stale first observation after reset/setup; crafting result slot counted as held | Settled start observation; slot 0 excluded |
| 12 | Review | Prompt quality: task-specific names, hard-coded kinds, unbounded digging | Rules: check the goal first, derive kinds, name by capability, never redeclare library names, stop at danger; guide: digging bounded at 8 blocks |

## Live after the fixes (2026-10-16)

| Run | Before (QA) | After |
|---|---|---|
| `wooden-pickaxe`, seed 12345, fresh library | false after 3 attempts | **true after 1** (68 s, $0.012) |
| `stone-pickaxe`, seed 12345, reusing `craftWoodenPickaxe` | — | **true after 3** (220 s, $0.110), every attempt from a clean start |

QA's other measurements (before the fixes): 16 task runs, $0.01–$0.13 each; prompt injection in the goal ignored; impossible
tasks stop at the attempt cap; the library is unchanged on failure; every telemetry line matches its run's trace.

## Open

- **Reuse is real but uneven.** Frozen runs on an unseen seed reused `craftWoodenPickaxe` (1 call, $0.013), but a stored
  stone skill failed where no stone was in sight and the model then wrote a new one. Skills are still large and
  monolithic; the evaluation (P4.2, several seeds) will measure how much reuse saves.
- **Learned skills depend on what their world shows** (stone in sight, wood kinds). The guide and prompt now push for
  derived kinds and bounded searching; P4.2's unseen seeds are the real test.
- **L2 may embellish free-text goals** (seen in P3.2 live: "craft me a wooden sword" → "…and give it to Fatih"; the
  bot has no hand-over primitive and the predicate only checks possession). The task text should not promise more than
  the predicate checks.
