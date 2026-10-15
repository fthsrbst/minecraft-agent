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
