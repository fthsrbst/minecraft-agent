/**
 * The scenario component: a separate plugin process for the evaluator only. It sets up and resets
 * test states over RCON. The agent's bot process never has this capability (AGENTS.md decision 15).
 * Methods: handshake, scenario.setup { player, spec }, scenario.reset { player }.
 */
import { readFileSync } from "node:fs";

import {
  ErrorCode,
  type Handler,
  type JsonObject,
  JsonRpcServer,
  RpcError,
  serveLines,
} from "./rpc/json-rpc.js";
import { isFailureReply, parsePlayer, resetCommands, setupCommands } from "./scenario/commands.js";
import { RconClient, RconError } from "./scenario/rcon.js";
import { freshWorld, parseSeed, type WorldConfig, WorldError } from "./scenario/world.js";

// stdout carries protocol messages only (see plugin-main.ts).
console.log = console.error;
console.info = console.error;

const RCON_TIMEOUT_MS = 5000;
const LOCAL_HOSTS: ReadonlySet<string> = new Set(["localhost", "127.0.0.1", "::1"]);

interface Manifest {
  readonly id: string;
  readonly version: string;
  readonly protocolVersion: string;
}

const manifest = JSON.parse(
  readFileSync(new URL("../plugin.json", import.meta.url), "utf8"),
) as Manifest;

// Module-level and reassigned inside functions, so TypeScript must not narrow it to `null` here.
let rcon = null as RconClient | null;

async function connectRcon(): Promise<RconClient> {
  if (rcon !== null) {
    return rcon;
  }
  const host = process.env.MC_RCON_HOST ?? "127.0.0.1";
  const port = Number(process.env.MC_RCON_PORT ?? "25575");
  const password = process.env.MC_RCON_PASSWORD ?? "";
  if (!LOCAL_HOSTS.has(host)) {
    throw new RpcError(ErrorCode.InvalidParams, `MC_RCON_HOST=${host} is not a local host.`);
  }
  if (password === "") {
    throw new RpcError(ErrorCode.NotReady, "MC_RCON_PASSWORD is not set; see .env.example.");
  }
  try {
    rcon = await RconClient.connect({ host, port, password, timeoutMs: RCON_TIMEOUT_MS });
  } catch (error: unknown) {
    throw new RpcError(ErrorCode.NotReady, error instanceof Error ? error.message : String(error));
  }
  return rcon;
}

// Setup, reset and world switches must not interleave (one RCON connection, one server), so all
// calls run one after another.
let queue: Promise<unknown> = Promise.resolve();

function serialized<T>(task: () => Promise<T>): Promise<T> {
  const next = queue.then(task);
  queue = next.catch(() => undefined);
  return next;
}

function run(commands: readonly string[]): Promise<JsonObject> {
  return serialized(() => runNow(commands));
}

const worldConfig: WorldConfig = {
  // The plugin lives in <repo>/plugins/minecraft; docker-compose.yml is at the repo root.
  composeDir: process.env.MC_COMPOSE_DIR ?? new URL("../../..", import.meta.url).pathname,
  service: "minecraft",
  container: "minecraft-agent-server",
};

function switchWorld(rawSeed: unknown): Promise<JsonObject> {
  let seed: number;
  try {
    seed = parseSeed(rawSeed);
  } catch (error: unknown) {
    throw new RpcError(
      ErrorCode.InvalidParams,
      error instanceof Error ? error.message : String(error),
    );
  }
  return serialized(async () => {
    // The server is about to restart; the old RCON connection would be dead anyway.
    rcon?.close();
    rcon = null;
    try {
      const world = await freshWorld(worldConfig, seed, process.env);
      await connectRcon();
      return { ok: true, ...world };
    } catch (error: unknown) {
      if (error instanceof WorldError) {
        throw new RpcError(ErrorCode.InternalError, error.message);
      }
      throw error;
    }
  });
}

/** Runs commands in order and stops at the first one the server rejects. */
async function runNow(commands: readonly string[]): Promise<JsonObject> {
  const client = await connectRcon();
  const results: JsonObject[] = [];
  for (const command of commands) {
    let reply: string;
    try {
      reply = await client.command(command);
    } catch (error: unknown) {
      rcon = null;
      const message = error instanceof RconError ? error.message : String(error);
      throw new RpcError(ErrorCode.InternalError, message, { command, done: results });
    }
    results.push({ command, reply });
    if (isFailureReply(reply, command)) {
      throw new RpcError(ErrorCode.InternalError, `Server rejected "${command}": ${reply}`, {
        command,
        reply,
        done: results,
      });
    }
  }
  return { ok: true, commands: results };
}

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
      await connectRcon();
      return {
        protocolVersion: manifest.protocolVersion,
        plugin: { id: manifest.id, version: manifest.version },
        component: "scenario",
        methods: ["handshake", "scenario.setup", "scenario.reset", "scenario.world"],
      };
    },
  ],
  [
    "scenario.setup",
    (params) => {
      const { spec = {} } = params;
      if (typeof spec !== "object" || spec === null || Array.isArray(spec)) {
        throw new RpcError(ErrorCode.InvalidParams, "scenario: `spec` must be an object.");
      }
      return run(setupCommands(parsePlayer(params.player), spec));
    },
  ],
  ["scenario.reset", (params) => run(resetCommands(parsePlayer(params.player), params.spawn))],
  ["scenario.world", (params) => switchWorld(params.seed)],
]);

const server = new JsonRpcServer(handlers, (line) => {
  process.stdout.write(`${line}\n`);
});

await serveLines(server, process.stdin);
rcon?.close();
