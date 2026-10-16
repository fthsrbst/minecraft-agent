# agent-core

The game-independent core (Python 3.13). It must never contain game, block or item names;
everything game-specific lives in a plugin under `plugins/<game>/` (see `AGENTS.md`).

```bash
uv sync                 # create .venv and install dev tools
uv run ruff check       # lint
uv run ruff format      # format
uv run pyright          # strict type check
uv run pytest           # tests
```

## Talking to a plugin

`agent_core.plugins.PluginClient` starts a plugin from its directory (`plugin.json`), and offers
`handshake()`, `observe()`, `act(primitive, args)` and `next_event()`. Every request has a timeout.
Demo against a running game server:

```bash
(cd ../plugins/minecraft && npm run build)
uv run python -m agent_core.bridge_demo ../plugins/minecraft
```

## LLM calls and telemetry

`agent_core.llm.LlmClient` is the only way the core calls an LLM. It picks the model by role
(`ModelRole.CODE` → Claude Sonnet 5.5, `ModelRole.TEXT` → Claude Haiku 5.5), enforces a timeout,
and writes one JSON line per call (success or failure) through `agent_core.telemetry`: trace id,
purpose, models, tokens, cost in USD, latency, request id. Prices live in `agent_core/llm/pricing.py`;
an unknown model gets `cost_usd: null`, never a guess.

```bash
uv run --env-file ../.env python -m agent_core.llm_demo   # needs ANTHROPIC_API_KEY in ../.env
```

## Predicates and scenarios

`agent_core.verifier` evaluates acceptance predicates (JSON: `has_item`, `near`, `compare`,
`all`, `any`, `not`) against an observation and answers `true`, `false` or `unknown`. A missing or
malformed field is `unknown`, and only `true` counts as success. `agent_core.scenarios` loads a
scenario file (`id`, `setup`, `predicate`); the `setup` block is interpreted by the plugin's
`scenario` component.

```bash
uv run --env-file ../.env python -m agent_core.scenario_demo ../plugins/minecraft \
  ../plugins/minecraft/scenarios/*.json --runs 2
```

For each scenario and run: reset → the predicate must be `false`, setup → it must become `true`.

## Task-run records

`agent_core.runs.TaskRun` opens a run (task, arm, seed, `world_instance_id`, visibility, models,
library snapshot, and a `trace_id` to pass to every LLM call of the run); `finish(verdict, ...)`
sums that trace's LLM calls from telemetry and returns a `TaskRunRecord`, which `RunRecorder`
appends as one JSON line. The evaluation report (P4.2, P5.1) is computed from these records.
`scenario_demo --seed N` runs every scenario in a fresh world of seed N and writes records to
`runs/scenario-demo.jsonl`.

## Running skills

`agent_core.skills.run_skill(plugin, code, args, timeout_s=...)` starts a skill in the plugin's
isolated executor and waits for its `skill.done` event; if the core gives up first it cancels the
run in the plugin. Demo:

```bash
uv run --env-file ../.env python -m agent_core.skill_demo ../plugins/minecraft \
  ../plugins/minecraft/skills/wooden-pickaxe.js --seed 20261119 \
  --predicate '{"type": "has_item", "item": "wooden_pickaxe"}'
```

## The Voyager loop and the skill library

`agent_core.voyager.loop.VoyagerAgent.solve(task, session, trace_id=...)` runs one task:

1. **Predicate first.** The task file's predicate, or one the LLM writes before any code; it must be `false` now
   (a goal that already holds cannot show that a skill did anything).
2. **Write.** Sonnet 5.5 gets the rules, the plugin's skill API and game guide (from the handshake), the task, the
   predicate, the current observation, matching library skills, and every earlier failure of this task.
3. **Run** the skill in the plugin's executor, with the library skills it calls defined in front of it.
4. **Verify** with the predicate (the skill's own report never counts). Success stores the skill; failure is fed
   back, up to 3 attempts.

`agent_core.library.SkillLibrary` keeps verified skills in SQLite: keyword search, dependency assembly, a
`snapshot_id` for run records, and a read-only mode for frozen evaluation arms.

```bash
uv run --env-file ../.env python -m agent_core.voyager_demo ../plugins/minecraft \
  ../plugins/minecraft/tasks/wooden-pickaxe.json ../plugins/minecraft/tasks/stone-pickaxe.json \
  --seed 20261119 --fresh-library
```
