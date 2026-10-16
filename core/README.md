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
