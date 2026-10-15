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
```

The bot reads `MC_HOST`, `MC_PORT` and `MC_USERNAME` from the repo-root `.env`. `MC_HOST` must be
local (`localhost`, `127.0.0.1`, `::1`); any other host is refused at startup.

TypeScript is pinned to 6.0: `typescript-eslint` 8.x does not support TypeScript 7 yet
(peer range `<6.1.0`).
