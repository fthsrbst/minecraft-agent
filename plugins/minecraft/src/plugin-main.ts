/**
 * Plugin process entry point. The core starts it (command from `plugin.json`) and talks to it over
 * newline-delimited JSON-RPC on stdin/stdout. Methods: handshake, observe, act; events are sent as
 * `event` notifications.
 */
import { readFileSync } from "node:fs";

import { ACT_PRIMITIVES, parseAction } from "./bridge/actions.js";
import { MinecraftRuntime } from "./bridge/minecraft-runtime.js";
import { parseObserveOptions, parseVisibility } from "./bridge/observation.js";
import { DEFAULT_TIMEOUT_MS, SkillBroker } from "./skills/broker.js";
import { createPrimitives, SKILL_API } from "./skills/primitives.js";
import { checkSkillSource, syntaxProblem } from "./skills/static-check.js";
import { ReflexEngine } from "./reflexes/engine.js";
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

// If the core goes away, writing to stdout fails with EPIPE; the plugin must exit, not crash noisily.
process.stdout.on("error", () => {
  process.exit(0);
});

interface Manifest {
  readonly id: string;
  readonly version: string;
  readonly protocolVersion: string;
  readonly game: JsonObject;
}

// plugin.json is the single source of the plugin's identity; it sits next to dist/.
const manifest = JSON.parse(
  readFileSync(new URL("../plugin.json", import.meta.url), "utf8"),
) as Manifest;

const visibility = parseVisibility(process.env.MC_VISIBILITY);
const skillGuide = readFileSync(new URL("../prompts/skill-guide.md", import.meta.url), "utf8");

const emit = (event: JsonObject): void => {
  server.notify("event", event);
  // Without a bot a skill can only fail slowly (primitives wait for their timeouts); stop it now.
  if (event.type === "disconnected" || event.type === "death") {
    skills.cancel();
  }
};
const runtime = new MinecraftRuntime(loadBotConfig(process.env), emit);
const skills = new SkillBroker(
  createPrimitives(() => runtime.liveBot, visibility),
  emit,
);

// L0 reflexes (P3.1): on by default; MC_REFLEXES=off disables them (e.g. for scripted tests).
let reflexes = null as ReflexEngine | null;
const reflexesEnabled = process.env.MC_REFLEXES !== "off";
runtime.onReady((bot) => {
  reflexes = new ReflexEngine(bot, {
    interruptWork: (reason) => {
      const skill = skills.cancel(undefined, `interrupted by ${reason}`);
      const action = runtime.interrupt();
      return skill || action;
    },
    working: () => skills.runningId !== null || runtime.busy,
    emit,
  });
  reflexes.setEnabled(reflexesEnabled);
});

/** An emergency reflex owns the bot until it is done (decision 13: safety first). */
function requireNoReflex(): void {
  if (reflexes?.busy === true) {
    throw new RpcError(ErrorCode.NotReady, "A reflex is handling an emergency; retry shortly.");
  }
}

/** A skill owns the bot's controls while it runs; single actions wait until it is done. */
function requireNoSkill(): void {
  const running = skills.runningId;
  if (running !== null) {
    throw new RpcError(
      ErrorCode.NotReady,
      `Skill ${running} is running; call skill.cancel or interrupt first.`,
    );
  }
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
      await runtime.connect(CONNECT_TIMEOUT_MS);
      return {
        protocolVersion: manifest.protocolVersion,
        plugin: { id: manifest.id, version: manifest.version },
        game: manifest.game,
        component: "main",
        visibility,
        methods: [
          "handshake",
          "observe",
          "act",
          "interrupt",
          "skill.run",
          "skill.check",
          "skill.cancel",
          "reflexes.set",
        ],
        primitives: ACT_PRIMITIVES,
        skillApi: SKILL_API,
        // Game knowledge for the code-writing prompt; the core inserts it without reading it.
        skillGuide,
      };
    },
  ],
  [
    "observe",
    (params) => {
      try {
        return runtime.observe(parseObserveOptions(params, visibility));
      } catch (error: unknown) {
        if (error instanceof RangeError) {
          throw new RpcError(ErrorCode.InvalidParams, error.message);
        }
        throw error;
      }
    },
  ],
  [
    "act",
    (params) => {
      requireNoReflex();
      requireNoSkill();
      return runtime.act(parseAction(params));
    },
  ],
  [
    "interrupt",
    () => {
      const skill = skills.cancel();
      const action = runtime.interrupt();
      return { interrupted: skill || action };
    },
  ],
  [
    "skill.run",
    (params) => {
      const { code, args = {}, timeoutMs = DEFAULT_TIMEOUT_MS } = params;
      if (typeof code !== "string") {
        throw new RpcError(ErrorCode.InvalidParams, "skill.run: `code` must be a string.");
      }
      if (typeof args !== "object" || args === null || Array.isArray(args)) {
        throw new RpcError(ErrorCode.InvalidParams, "skill.run: `args` must be an object.");
      }
      if (typeof timeoutMs !== "number") {
        throw new RpcError(ErrorCode.InvalidParams, "skill.run: `timeoutMs` must be a number.");
      }
      // Fail before starting a process when the bot is not there to act.
      runtime.assertReady();
      requireNoReflex();
      if (runtime.busy) {
        throw new RpcError(ErrorCode.NotReady, "An action is running; wait for it or interrupt.");
      }
      return { runId: skills.start(code, args, timeoutMs) };
    },
  ],
  [
    "reflexes.set",
    (params) => {
      if (typeof params.enabled !== "boolean") {
        throw new RpcError(ErrorCode.InvalidParams, "reflexes.set: `enabled` must be a boolean.");
      }
      reflexes?.setEnabled(params.enabled);
      return { enabled: params.enabled };
    },
  ],
  [
    "skill.check",
    (params) => {
      const { code } = params;
      if (typeof code !== "string") {
        throw new RpcError(ErrorCode.InvalidParams, "skill.check: `code` must be a string.");
      }
      const problems = checkSkillSource(code);
      const syntax = syntaxProblem(code);
      const all = syntax === null ? problems : [...problems, syntax];
      return all.length === 0 ? { ok: true } : { ok: false, problem: all.join("; ") };
    },
  ],
  [
    "skill.cancel",
    (params) => {
      const { runId } = params;
      if (runId !== undefined && typeof runId !== "string") {
        throw new RpcError(ErrorCode.InvalidParams, "skill.cancel: `runId` must be a string.");
      }
      return { cancelled: skills.cancel(runId) };
    },
  ],
]);

const server = new JsonRpcServer(handlers, (line) => {
  process.stdout.write(`${line}\n`);
});

const shutdown = (reason: string): void => {
  skills.cancel();
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
