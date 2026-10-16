/**
 * Owns the Mineflayer bot for the plugin process: connects it, turns its state into JSON
 * observations, executes validated actions, and forwards game events to the core.
 */
import { type Bot, createBot } from "mineflayer";

import type { BotConfig } from "../bot-config.js";
import { GAME_VERSION } from "../plugin-info.js";
import { ErrorCode, type JsonObject, RpcError } from "../rpc/json-rpc.js";
import type { Action } from "./actions.js";

export type EmitEvent = (event: JsonObject) => void;

const round = (value: number): number => Math.round(value * 100) / 100;

export class MinecraftRuntime {
  private bot: Bot | null = null;
  private connecting: Promise<void> | null = null;

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

  observe(): JsonObject {
    const bot = this.requireBot();
    const { x, y, z } = bot.entity.position;
    return {
      username: bot.username,
      position: { x: round(x), y: round(y), z: round(z) },
      yaw: round(bot.entity.yaw),
      dimension: bot.game.dimension,
      health: bot.health,
      food: bot.food,
      timeOfDay: bot.time.timeOfDay,
      inventory: bot.inventory.items().map((item) => ({ name: item.name, count: item.count })),
    };
  }

  async act(action: Action): Promise<JsonObject> {
    const bot = this.requireBot();
    switch (action.primitive) {
      case "chat":
        bot.chat(action.text);
        return { ok: true };
      case "move": {
        bot.setControlState(action.direction, true);
        bot.setControlState("jump", action.jump);
        try {
          await new Promise((resolve) => setTimeout(resolve, action.durationMs));
        } finally {
          bot.clearControlStates();
        }
        const { position } = this.observe();
        return { ok: true, position: position ?? null };
      }
    }
  }

  quit(reason: string): void {
    this.bot?.quit(reason);
  }

  private requireBot(): Bot {
    if (this.bot?.entity === undefined) {
      throw new RpcError(ErrorCode.NotReady, "The bot has not spawned yet; call handshake first.");
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

    return new Promise<void>((resolve, reject) => {
      const fail = (message: string): void => {
        clearTimeout(timer);
        bot.removeAllListeners();
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
      bot.once("spawn", () => {
        clearTimeout(timer);
        bot.removeAllListeners("error");
        bot.removeAllListeners("kicked");
        this.bot = bot;
        this.forwardEvents(bot);
        resolve();
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
      this.bot = null;
      this.connecting = null;
      this.emit({ type: "disconnected", reason });
    });
  }
}
