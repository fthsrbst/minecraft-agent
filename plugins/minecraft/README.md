# plugin-minecraft

The Minecraft game plugin (TypeScript, Node 22). It runs as a separate process and talks to the
core over versioned JSON-RPC (plan item P1.4); the core never imports this code.

```bash
npm ci                  # install exactly package-lock.json
npm run lint            # eslint (type-aware)
npm run format:check    # prettier
npm run typecheck       # tsc --noEmit, strict
npm test                # vitest
npm run build           # compile src/ to dist/
npm run hello           # P1.2 hello bot; needs `docker compose up` at the repo root
node dist/plugin-main.js # the plugin process; normally started by the core (see plugin.json)
```

The bot reads `MC_HOST`, `MC_PORT` and `MC_USERNAME` from the repo-root `.env`. `MC_HOST` must be
local (`localhost`, `127.0.0.1`, `::1`); any other host is refused at startup.

TypeScript is pinned to 6.0: `typescript-eslint` 8.x does not support TypeScript 7 yet
(peer range `<6.1.0`).

## Protocol

`plugin.json` is the manifest the core reads: id, version, protocol version (`gpp/1`), the command
that starts each process, and the environment variables each process may receive (`env`). The
process speaks newline-delimited JSON-RPC 2.0 on stdin/stdout; stdout carries protocol messages
only, logs go to stderr.

| Method      | Params                                                          | Result                                                                                       |
| ----------- | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `handshake` | `{ protocolVersion }`                                           | identity, game, `visibility`, `methods`, `primitives` (with JSON Schemas); joins the server  |
| `observe`   | `{ nearby? = true, radius? = 16 }`                              | `username, tick, visibility, position, yaw, dimension, health, food, timeOfDay, standingOn,` |
|             |                                                                 | `equipment, inventory` and, with `nearby`, `nearbyBlocks` (grouped) and `nearbyEntities`     |
| `act`       | `{ primitive: "chat", args: { text } }`                         | `{ ok }`; no `/` commands, no control characters                                             |
| `act`       | `{ primitive: "move", args: { direction, durationMs, jump? } }` | `{ ok, interrupted, position }`                                                              |
| `interrupt` | –                                                               | `{ interrupted }`: stops the running action at once                                          |

Events arrive as `event` notifications: `chat`, `health`, `death`, `kicked`, `error`, `disconnected`.

`MC_VISIBILITY=fair` (default, used for evaluation) reports only blocks with a face open to air;
`full` reports every block in range (AGENTS.md decision 15). An observation with `nearby` takes
about 80 ms; use `nearby: false` (under 1 ms) for fast loops.

## Scenario component (evaluator only)

`node dist/scenario-main.js` (manifest component `scenario`) sets up and resets test states over
RCON and switches worlds. It is a separate process so the agent's bot never holds server-console
power (AGENTS.md decision 15). It reads `MC_RCON_HOST` (local only), `MC_RCON_PORT`,
`MC_RCON_PASSWORD` and `MC_COMPOSE_DIR` (default: the repository root).

| Method           | Params                                                                                            |
| ---------------- | ------------------------------------------------------------------------------------------------- |
| `scenario.setup` | `{ player, spec: { clear?, fill?, place?, teleport?, give?, summon?, time?, weather? } }`         |
| `scenario.reset` | `{ player, spawn? }`: scenario mobs and item drops removed, inventory and effects cleared,        |
|                  | healed and fed, day, clear weather, and back at `spawn` if given                                  |
| `scenario.world` | `{ seed }`: restores a fresh copy of that seed's world and restarts the server (~7 s; the         |
|                  | first call per seed generates it, ~18 s). Returns `worldInstanceId`. The bot must handshake again |

Every value is validated before it reaches a command (items, blocks and entities are checked
against the 1.21.11 data), summoned entities are tagged so reset removes exactly them, and a server
reply such as "No player was found" fails the call. Scenario files live in `scenarios/`.
