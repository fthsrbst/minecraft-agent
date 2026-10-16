/**
 * Skill broker: runs one skill at a time in a fresh executor process and performs the primitives
 * the skill asks for. The broker owns the bot (through the primitives table); the executor owns
 * nothing, so killing it on timeout or cancel always leaves the bot alive (AGENTS.md decision 8).
 *
 * `start` returns a run id at once; the outcome arrives later as a `skill.done` event, because a
 * skill can run for minutes and must stay interruptible.
 */
import { type ChildProcess, fork } from "node:child_process";
import { randomUUID } from "node:crypto";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { ErrorCode, type JsonObject, type JsonValue, RpcError } from "../rpc/json-rpc.js";
import type { FromExecutor, ToExecutor } from "./protocol.js";
import { checkSkillSource } from "./static-check.js";

/** A game action the skill may request. It must stop promptly when `signal` aborts. */
export type Primitive = (args: JsonObject, signal: AbortSignal) => Promise<JsonValue>;

export type SkillStatus = "ok" | "error" | "timeout" | "cancelled" | "crashed";

export const DEFAULT_TIMEOUT_MS = 120_000;
export const MAX_TIMEOUT_MS = 600_000;
const MAX_PRIMITIVE_CALLS = 500;
const MAX_LOG_LINES = 100;
const EXECUTOR_MEMORY_MB = 256;

// Tests import this module from src/ (TypeScript); production runs dist/ (JavaScript).
const executorUrl = new URL(
  import.meta.url.endsWith(".ts") ? "./executor.ts" : "./executor.js",
  import.meta.url,
);

interface ActiveRun {
  readonly runId: string;
  readonly child: ChildProcess;
  readonly started: number;
  readonly timer: NodeJS.Timeout;
  readonly abort: AbortController;
  readonly logs: string[];
  readonly stderr: string[];
  primitiveCalls: number;
  // Primitives run one at a time: they share the bot's controls and inventory.
  queue: Promise<unknown>;
}

export class SkillBroker {
  private active: ActiveRun | null = null;

  constructor(
    private readonly primitives: ReadonlyMap<string, Primitive>,
    private readonly emit: (event: JsonObject) => void,
  ) {}

  get runningId(): string | null {
    return this.active?.runId ?? null;
  }

  /** Starts a skill; returns its run id. Fails fast on a busy broker or code that can never run. */
  start(code: string, args: JsonObject, timeoutMs: number): string {
    if (this.active !== null) {
      throw new RpcError(ErrorCode.NotReady, `A skill is already running (${this.active.runId}).`);
    }
    const problems = checkSkillSource(code);
    if (problems.length > 0) {
      throw new RpcError(ErrorCode.InvalidParams, `skill rejected: ${problems.join("; ")}.`, {
        problems,
      });
    }
    if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > MAX_TIMEOUT_MS) {
      throw new RpcError(
        ErrorCode.InvalidParams,
        `timeoutMs must be an integer from 1 to ${String(MAX_TIMEOUT_MS)}.`,
      );
    }

    const child = fork(fileURLToPath(executorUrl), [], {
      // Node's permission model: the executor may read its own code and nothing else; no file
      // writes, no child processes, no workers, no native addons. No environment: no secrets.
      execArgv: [
        "--permission",
        `--allow-fs-read=${dirname(fileURLToPath(executorUrl))}`,
        `--max-old-space-size=${String(EXECUTOR_MEMORY_MB)}`,
        "--disallow-code-generation-from-strings",
      ],
      env: {},
      stdio: ["ignore", "ignore", "pipe", "ipc"],
      serialization: "json",
    });
    const runId = randomUUID();
    const run: ActiveRun = {
      runId,
      child,
      started: Date.now(),
      timer: setTimeout(() => {
        this.finish(run, "timeout", null, `no result within ${String(timeoutMs)} ms`);
      }, timeoutMs),
      abort: new AbortController(),
      logs: [],
      stderr: [],
      primitiveCalls: 0,
      queue: Promise.resolve(),
    };
    this.active = run;

    child.stderr?.setEncoding("utf8");
    child.stderr?.on("data", (chunk: string) => {
      run.stderr.push(...chunk.split("\n").filter((line) => line !== ""));
      run.stderr.splice(0, Math.max(0, run.stderr.length - 20));
    });
    child.on("message", (message: FromExecutor) => {
      this.onMessage(run, message);
    });
    child.on("exit", (code, signal) => {
      const tail = run.stderr.join("\n");
      this.finish(run, "crashed", null, `executor exited (${String(code ?? signal)}). ${tail}`);
    });
    child.on("error", (error) => {
      this.finish(run, "crashed", null, `executor error: ${error.message}`);
    });

    this.emit({ type: "skill.started", runId });
    const start: ToExecutor = { type: "run", code, args };
    child.send(start);
    return runId;
  }

  /** Stops the running skill (or the one with this id); false if nothing matched. */
  cancel(runId?: string): boolean {
    const run = this.active;
    if (run === null || (runId !== undefined && run.runId !== runId)) {
      return false;
    }
    this.finish(run, "cancelled", null, "cancelled");
    return true;
  }

  private onMessage(run: ActiveRun, message: FromExecutor): void {
    if (this.active !== run) {
      return; // late message from a run that already finished
    }
    switch (message.type) {
      case "log":
        if (run.logs.length < MAX_LOG_LINES) {
          run.logs.push(message.message);
        }
        this.emit({ type: "skill.log", runId: run.runId, message: message.message });
        return;
      case "done":
        this.finish(
          run,
          message.ok ? "ok" : "error",
          message.result ?? null,
          message.error ?? null,
        );
        return;
      case "call":
        run.queue = run.queue.then(() => this.perform(run, message.id, message.name, message.args));
        return;
    }
  }

  private async perform(run: ActiveRun, id: number, name: string, args: JsonObject): Promise<void> {
    const reply = (ok: boolean, value: JsonValue, error?: string): void => {
      if (this.active === run && run.child.connected) {
        const message: ToExecutor =
          error === undefined ? { type: "reply", id, ok, value } : { type: "reply", id, ok, error };
        run.child.send(message);
      }
    };
    const primitive = this.primitives.get(name);
    if (primitive === undefined) {
      reply(false, null, `unknown primitive ${name}`);
      return;
    }
    run.primitiveCalls += 1;
    if (run.primitiveCalls > MAX_PRIMITIVE_CALLS) {
      reply(false, null, `more than ${String(MAX_PRIMITIVE_CALLS)} primitive calls`);
      return;
    }
    try {
      reply(true, await primitive(args, run.abort.signal));
    } catch (error: unknown) {
      reply(false, null, error instanceof Error ? error.message : String(error));
    }
  }

  private finish(
    run: ActiveRun,
    status: SkillStatus,
    result: JsonValue,
    error: string | null,
  ): void {
    if (this.active !== run) {
      return;
    }
    this.active = null;
    clearTimeout(run.timer);
    run.abort.abort();
    if (run.child.exitCode === null && run.child.signalCode === null) {
      run.child.kill("SIGKILL");
    }
    this.emit({
      type: "skill.done",
      runId: run.runId,
      status,
      result,
      error,
      durationMs: Date.now() - run.started,
      primitiveCalls: run.primitiveCalls,
      logs: run.logs,
    });
  }
}
