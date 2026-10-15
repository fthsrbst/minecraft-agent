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

`plugin.json` is the manifest the core reads: id, version, protocol version (`gpp/1`) and the command
that starts the plugin. The process speaks newline-delimited JSON-RPC 2.0 on stdin/stdout; stdout
carries protocol messages only, logs go to stderr.

| Method      | Params                                                          | Result                                                             |
| ----------- | --------------------------------------------------------------- | ------------------------------------------------------------------ |
| `handshake` | `{ protocolVersion }`                                           | identity, game, methods, primitives (joins the server first)       |
| `observe`   | –                                                               | `{ position, yaw, dimension, health, food, timeOfDay, inventory }` |
| `act`       | `{ primitive: "chat", args: { text } }`                         | `{ ok }`                                                           |
| `act`       | `{ primitive: "move", args: { direction, durationMs, jump? } }` | `{ ok, position }`                                                 |

Events arrive as `event` notifications: `chat`, `health`, `death`, `kicked`, `error`, `disconnected`.
