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
