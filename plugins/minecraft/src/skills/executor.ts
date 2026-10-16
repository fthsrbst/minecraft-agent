/**
 * Skill executor: a child process that runs one skill and exits. It holds no bot, no sockets and
 * no environment; every game action is a `call` message the broker validates and performs. The
 * broker kills this process on timeout or cancel, so even `while (true) {}` cannot stall the bot.
 *
 * The code runs as the body of an async function with `bot`, `args` and `log` in scope, inside a
 * `vm` context without `process` or `require`. (vm is not a security boundary on its own; the
 * process boundary, Node's permission model and the broker's limits are.)
 */
import { createContext, Script } from "node:vm";

import type { JsonObject, JsonValue } from "../rpc/json-rpc.js";
import type { FromExecutor, ToExecutor } from "./protocol.js";

const MAX_LOG_LINES = 100;
const MAX_LOG_LINE = 500;
const MAX_RESULT_CHARS = 20_000;

// The objects handed to the skill (`bot`, `args`, `log`, replies) come from this realm. Without
// this, a skill could add `Object.prototype.toJSON` and rewrite every message this process sends
// (e.g. forge a `done` result). Frozen before any skill code runs.
for (const value of [Object, Array, Function, Promise, Error, String, Number, Boolean, Symbol]) {
  Object.freeze(value.prototype);
  Object.freeze(value);
}
Object.freeze(JSON);

let nextId = 1;
let logLines = 0;
const pending = new Map<number, { resolve: (v: JsonValue) => void; reject: (e: Error) => void }>();

function send(message: FromExecutor): void {
  process.send?.(message);
}

function call(name: string, args: JsonObject): Promise<JsonValue> {
  const id = nextId++;
  return new Promise<JsonValue>((resolve, reject) => {
    pending.set(id, { resolve, reject });
    send({ type: "call", id, name, args });
  });
}

// The DOM-free lib types JSON.stringify as always returning a string; it does not.
const toJson: (value: unknown) => string | undefined = JSON.stringify;

function stringify(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  try {
    // JSON.stringify returns undefined for undefined, functions and symbols.
    return toJson(value) ?? String(value);
  } catch {
    return String(value);
  }
}

// Errors thrown by skill code come from the vm context's realm, where `instanceof Error` is false.
function describeError(error: unknown): string {
  if (typeof error === "object" && error !== null && "message" in error) {
    const name = "name" in error ? String(error.name) : "Error";
    return `${name}: ${String(error.message)}`;
  }
  return `thrown value: ${stringify(error)}`;
}

/** The API skill code sees as `bot`. Positional arguments map to named primitive arguments. */
const api = Object.freeze({
  observe: (options: JsonObject = {}) => call("observe", options),
  goTo: (x: number, y: number, z: number, options: JsonObject = {}) =>
    call("goTo", { ...options, x, y, z }),
  collect: (block: string, count = 1, options: JsonObject = {}) =>
    call("collect", { ...options, block, count }),
  craft: (item: string, count = 1) => call("craft", { item, count }),
  place: (item: string, position?: { x: number; y: number; z: number }) =>
    call("place", position === undefined ? { item } : { item, ...position }),
  equip: (item: string) => call("equip", { item }),
  dig: (x: number, y: number, z: number) => call("dig", { x, y, z }),
  chat: (text: string) => call("chat", { text }),
  wait: (ms: number) => call("wait", { ms }),
});

function log(...parts: unknown[]): void {
  // A log loop must not flood the broker; the first lines are the useful ones.
  if (logLines >= MAX_LOG_LINES) {
    return;
  }
  logLines += 1;
  send({ type: "log", message: parts.map(stringify).join(" ").slice(0, MAX_LOG_LINE) });
}

function finish(result: unknown): void {
  const text = result === undefined ? "null" : stringify(result);
  if (text.length > MAX_RESULT_CHARS) {
    const error = `result is larger than ${String(MAX_RESULT_CHARS)} characters`;
    send({ type: "done", ok: false, error });
    return;
  }
  let value: JsonValue;
  try {
    value = JSON.parse(text) as JsonValue;
  } catch {
    value = text; // not JSON (e.g. a function): report its text
  }
  send({ type: "done", ok: true, result: value });
}

async function run(code: string, args: JsonObject): Promise<void> {
  const context = createContext(
    { bot: api, args: Object.freeze({ ...args }), log },
    // The process flag only covers the main context; the skill's own context needs it too, or
    // `(async () => {}).constructor("...")` would compile new code from a string.
    { codeGeneration: { strings: false, wasm: false } },
  );
  try {
    const script = new Script(`(async () => {\n${code}\n})()`, { filename: "skill.js" });
    // No vm timeout: the broker's deadline ends every run, sync loops included, with an honest
    // "timeout" status (a vm timeout would report an ordinary error).
    finish(await script.runInContext(context));
  } catch (error: unknown) {
    send({ type: "done", ok: false, error: describeError(error).slice(0, 2_000) });
  }
}

// The broker is gone (plugin crashed or was killed): nobody can use the result, so stop. A CPU
// loop blocks this handler; the CPU-time limit the broker sets (ulimit -t) ends that case.
// A skill that forgets to await a failing primitive must not crash the executor; the run goes on
// and the rejection is written to the run's log.
process.on("unhandledRejection", (reason: unknown) => {
  log("unhandled rejection:", describeError(reason));
});

process.on("disconnect", () => {
  process.exit(1);
});

process.on("message", (message: ToExecutor) => {
  if (message.type === "run") {
    run(message.code, message.args).catch((error: unknown) => {
      send({ type: "done", ok: false, error: describeError(error).slice(0, 2_000) });
    });
    return;
  }
  const waiter = pending.get(message.id);
  if (waiter === undefined) {
    return;
  }
  pending.delete(message.id);
  if (message.ok) {
    waiter.resolve(message.value ?? null);
  } else {
    waiter.reject(new Error(message.error ?? "primitive failed"));
  }
});
