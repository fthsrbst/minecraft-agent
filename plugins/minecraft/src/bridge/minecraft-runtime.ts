/**
 * Owns the Mineflayer bot for the plugin process: connects it, turns its state into JSON
 * observations, executes validated actions, and forwards game events to the core.
 */
import { type Bot, createBot } from "mineflayer";
import { plugin as collectBlock } from "mineflayer-collectblock";
import pathfinderModule from "mineflayer-pathfinder";

import type { BotConfig } from "../bot-config.js";
import { GAME_VERSION } from "../plugin-info.js";
import { ErrorCode, type JsonObject, RpcError } from "../rpc/json-rpc.js";
import type { Action } from "./actions.js";
import { buildObservation, type ObserveOptions } from "./observation.js";

export type EmitEvent = (event: JsonObject) => void;

const CHUNK_WAIT_MS = 10_000;
const { pathfinder, Movements } = pathfinderModule;

export class MinecraftRuntime {
  private bot: Bot | null = null;
  private connecting: Promise<void> | null = null;
  private lastDisconnect: string | null = null;
  // Actions share the bot's control state, so they run one at a time in arrival order.
  private actQueue: Promise<unknown> = Promise.resolve();
  private currentAction: AbortController | null = null;
  private pendingActs = 0;
  // Bumped by interrupt(): queued actions from before the interrupt are dropped, not run late.
  private generation = 0;
  private readyListeners: ((bot: Bot) => void)[] = [];

  constructor(
    private readonly config: BotConfig,
    private readonly emit: EmitEvent,
  ) {}

  /** Joins the server and resolves once the bot has spawned. Safe to call more than once. */
  connect(timeoutMs: number): Promise<void> {
    this.connecting ??= this.startBot(timeoutMs).catch((error: unknown) => {
      // Allow a later handshake to retry after a failed connection.
      this.connecting = null;
      throw error;
    });
    return this.connecting;
  }

  observe(options: ObserveOptions): JsonObject {
    return buildObservation(this.requireBot(), options);
  }

  /** Called with the bot each time it has spawned and loaded its surroundings. */
  onReady(listener: (bot: Bot) => void): void {
    this.readyListeners.push(listener);
  }

  /** True while an `act` is running or queued. */
  get busy(): boolean {
    return this.currentAction !== null || this.pendingActs > 0;
  }

  /** Throws NotReady when the bot is not connected and spawned. */
  assertReady(): void {
    this.requireBot();
  }

  /** The connected bot, for in-process primitives (the skill broker). */
  get liveBot(): Bot {
    return this.requireBot();
  }

  /** Stops the running action at once and drops queued ones; they resolve `interrupted: true`. */
  interrupt(): boolean {
    this.generation += 1;
    if (this.currentAction === null) {
      return this.pendingActs > 0;
    }
    this.currentAction.abort();
    this.bot?.clearControlStates();
    return true;
  }

  act(action: Action): Promise<JsonObject> {
    this.pendingActs += 1;
    const generation = this.generation;
    const run = this.actQueue
      .then(() =>
        generation === this.generation
          ? this.runAction(action)
          : Promise.resolve<JsonObject>({ ok: false, interrupted: true }),
      )
      .finally(() => {
        this.pendingActs -= 1;
      });
    this.actQueue = run.catch(() => undefined);
    return run;
  }

  private async runAction(action: Action): Promise<JsonObject> {
    const bot = this.requireBot();
    switch (action.primitive) {
      case "chat":
        bot.chat(action.text);
        return { ok: true };
      case "move": {
        const controller = new AbortController();
        this.currentAction = controller;
        bot.setControlState(action.direction, true);
        bot.setControlState("jump", action.jump);
        try {
          await new Promise<void>((resolve) => {
            const timer = setTimeout(resolve, action.durationMs);
            controller.signal.addEventListener("abort", () => {
              clearTimeout(timer);
              resolve();
            });
          });
        } finally {
          bot.clearControlStates();
          this.currentAction = null;
        }
        const { x, y, z } = bot.entity.position;
        return {
          ok: !controller.signal.aborted,
          interrupted: controller.signal.aborted,
          position: {
            x: Math.round(x * 100) / 100,
            y: Math.round(y * 100) / 100,
            z: Math.round(z * 100) / 100,
          },
        };
      }
    }
  }

  quit(reason: string): void {
    this.bot?.quit(reason);
  }

  private requireBot(): Bot {
    if (this.bot?.entity === undefined) {
      const why =
        this.lastDisconnect === null
          ? "The bot has not spawned yet; call handshake first."
          : `The bot is disconnected (${this.lastDisconnect}); call handshake to reconnect.`;
      throw new RpcError(ErrorCode.NotReady, why);
    }
    return this.bot;
  }

  private startBot(timeoutMs: number): Promise<void> {
    const bot = createBot({
      host: this.config.host,
      port: this.config.port,
      username: this.config.username,
      // Offline mode: no Microsoft login (the server is localhost-only, AGENTS.md decision 4).
      auth: "offline",
      version: GAME_VERSION,
    });
    bot.loadPlugin(pathfinder);
    bot.loadPlugin(collectBlock);

    return new Promise<void>((resolve, reject) => {
      let settled = false;
      const fail = (message: string): void => {
        if (settled) {
          return;
        }
        settled = true;
        this.lastDisconnect = null;
        clearTimeout(timer);
        bot.removeAllListeners();
        // Without an error listener a late socket error would crash the whole plugin process.
        bot.on("error", () => undefined);
        bot.end();
        reject(new RpcError(ErrorCode.NotReady, message));
      };
      const timer = setTimeout(() => {
        fail(
          `No spawn within ${String(timeoutMs)} ms; is the server running on ${this.config.host}:${String(this.config.port)}?`,
        );
      }, timeoutMs);

      bot.once("error", (error) => {
        fail(`Connection error: ${error.message}`);
      });
      bot.once("kicked", (reason) => {
        fail(`Kicked while joining: ${JSON.stringify(reason)}`);
      });
      bot.once("end", (reason) => {
        fail(`Disconnected while joining: ${reason}`);
      });
      bot.once("spawn", () => {
        settled = true;
        clearTimeout(timer);
        bot.removeAllListeners("error");
        bot.removeAllListeners("kicked");
        bot.removeAllListeners("end");
        this.bot = bot;
        this.forwardEvents(bot);
        // Skill primitives navigate with the pathfinder and mine with collectblock (P2.3).
        bot.pathfinder.setMovements(new Movements(bot));
        // The default 5 s planning budget fails in dense forest ("Took to long to decide path").
        bot.pathfinder.thinkTimeout = 10_000;
        // Spawn arrives before the surrounding chunks; an observation taken now would see no blocks.
        // The wait is bounded so a slow server delays the handshake but never hangs it.
        void Promise.race([
          bot.waitForChunksToLoad(),
          new Promise((done) => setTimeout(done, CHUNK_WAIT_MS)),
        ]).then(() => {
          for (const listener of this.readyListeners) {
            listener(bot);
          }
          resolve();
        });
      });
    });
  }

  private forwardEvents(bot: Bot): void {
    bot.on("chat", (sender, message) => {
      if (sender !== bot.username) {
        this.emit({ type: "chat", sender, message });
      }
    });
    let last = { health: bot.health, food: bot.food };
    bot.on("health", () => {
      if (bot.health !== last.health || bot.food !== last.food) {
        last = { health: bot.health, food: bot.food };
        this.emit({ type: "health", ...last });
      }
    });
    bot.on("death", () => {
      this.emit({ type: "death" });
    });
    bot.on("kicked", (reason) => {
      this.emit({ type: "kicked", reason: JSON.stringify(reason) });
    });
    bot.on("error", (error) => {
      this.emit({ type: "error", message: error.message });
    });
    bot.on("end", (reason) => {
      this.lastDisconnect = reason;
      this.bot = null;
      this.connecting = null;
      this.emit({ type: "disconnected", reason });
    });
  }
}
