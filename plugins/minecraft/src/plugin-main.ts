/**
 * Plugin process entry point. The core starts it (command from `plugin.json`) and talks to it over
 * newline-delimited JSON-RPC on stdin/stdout. Methods: handshake, observe, act; events are sent as
 * `event` notifications.
 */
import { readFileSync } from "node:fs";

import { parseAction } from "./bridge/actions.js";
import { MinecraftRuntime } from "./bridge/minecraft-runtime.js";
import { loadBotConfig } from "./bot-config.js";
import {
  ErrorCode,
  type Handler,
  type JsonObject,
  JsonRpcServer,
  RpcError,
  serveLines,
} from "./rpc/json-rpc.js";

// stdout carries protocol messages only. Libraries that log with console.log would corrupt the
// stream, so all console output goes to stderr, which the core forwards to its log.
console.log = console.error;
console.info = console.error;

const CONNECT_TIMEOUT_MS = 60_000;

interface Manifest {
  readonly id: string;
  readonly version: string;
  readonly protocolVersion: string;
  readonly game: JsonObject;
  readonly capabilities: string[];
}

// plugin.json is the single source of the plugin's identity; it sits next to dist/.
const manifest = JSON.parse(
  readFileSync(new URL("../plugin.json", import.meta.url), "utf8"),
) as Manifest;

const runtime = new MinecraftRuntime(loadBotConfig(process.env), (event) => {
  server.notify("event", event);
});

const handlers = new Map<string, Handler>([
  [
    "handshake",
    async (params) => {
      if (params.protocolVersion !== manifest.protocolVersion) {
        throw new RpcError(
          ErrorCode.InvalidParams,
          `Protocol mismatch: core speaks ${JSON.stringify(params.protocolVersion ?? null)}, plugin speaks ${manifest.protocolVersion}.`,
        );
      }
      await runtime.connect(CONNECT_TIMEOUT_MS);
      return {
        protocolVersion: manifest.protocolVersion,
        plugin: { id: manifest.id, version: manifest.version },
        game: manifest.game,
        capabilities: manifest.capabilities,
        methods: ["handshake", "observe", "act"],
        primitives: ["chat", "move"],
      };
    },
  ],
  ["observe", () => runtime.observe()],
  ["act", (params) => runtime.act(parseAction(params))],
]);

const server = new JsonRpcServer(handlers, (line) => {
  process.stdout.write(`${line}\n`);
});

const shutdown = (reason: string): void => {
  runtime.quit(reason);
  // Give the quit packet a moment to leave before the process exits.
  setTimeout(() => process.exit(0), 200).unref();
};
process.once("SIGTERM", () => {
  shutdown("terminated by core");
});
process.once("SIGINT", () => {
  shutdown("interrupted");
});

// The core closing stdin means it is gone; the plugin must not outlive it.
await serveLines(server, process.stdin);
shutdown("core closed the connection");
