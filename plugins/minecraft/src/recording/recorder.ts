/**
 * Watches a demonstrator from the bot's side (the thin v1 of research.md §4.5: a watcher, not the
 * recording proxy). It sees block changes near the demonstrator and their `//` chat notes; it
 * cannot see their inventory or crafting. Changes are *observed* world changes, not the player's
 * requests: a change near them is attributed to them, which a falling block or a mob can fool, so
 * only changes within reach of the demonstrator at that moment count.
 */
import type { Bot } from "mineflayer";
import type { Block } from "prismarine-block";

import { type BlockEvent, type Note, type Recording } from "./blueprint.js";
import { type Cell, type Facing, facingFromYaw, toRelative } from "./frame.js";

// A player reaches about 4.5 blocks from the eyes; a little more covers the feet-to-block distance.
const REACH = 6;
const MAX_EVENTS = 2_000;
const MAX_NOTES = 50;
const MAX_NOTE_LENGTH = 200;
export const MAX_RECORDING_MS = 10 * 60_000;
export const NOTE_PREFIX = "//";

export class RecordError extends Error {}

interface Session {
  readonly player: string;
  readonly anchor: Cell;
  readonly facing: Facing;
  readonly started: number;
  readonly events: BlockEvent[];
  readonly notes: Note[];
  truncated: boolean;
  readonly stop: () => void;
}

export class Recorder {
  private session: Session | null = null;

  constructor(private readonly getBot: () => Bot) {}

  get recording(): string | null {
    return this.session?.player ?? null;
  }

  start(player: string): { anchor: Cell; facing: Facing } {
    if (this.session !== null) {
      throw new RecordError(`already recording ${this.session.player}; stop that first`);
    }
    const bot = this.getBot();
    const entity = bot.players[player]?.entity;
    if (entity === undefined) {
      throw new RecordError(`cannot see ${player}; come closer so the bot can watch`);
    }
    const anchor = cellOf(entity.position);
    const facing = facingFromYaw(entity.yaw);
    const started = performance.now();
    const events: BlockEvent[] = [];
    const notes: Note[] = [];
    const onBlock = (before: Block | null, after: Block): void => {
      const current = bot.players[player]?.entity;
      if (session.truncated || current === undefined) {
        return;
      }
      if (after.position.offset(0.5, 0.5, 0.5).distanceTo(current.position) > REACH) {
        return;
      }
      if (events.length >= MAX_EVENTS) {
        session.truncated = true;
        return;
      }
      const from = before?.name ?? "air";
      if (from === after.name) {
        return;
      }
      events.push({
        ...toRelative(cellOf(after.position), anchor, facing),
        t: Math.round(performance.now() - started),
        from,
        to: after.name,
      });
    };
    const onChat = (sender: string, message: string): void => {
      if (sender !== player || !message.startsWith(NOTE_PREFIX) || notes.length >= MAX_NOTES) {
        return;
      }
      const text = message.slice(NOTE_PREFIX.length).trim().slice(0, MAX_NOTE_LENGTH);
      if (text.length > 0) {
        notes.push({ t: Math.round(performance.now() - started), text });
      }
    };
    const limit = setTimeout(() => {
      session.truncated = true;
    }, MAX_RECORDING_MS);
    bot.on("blockUpdate", onBlock);
    bot.on("chat", onChat);
    const session: Session = {
      player,
      anchor,
      facing,
      started,
      events,
      notes,
      truncated: false,
      stop: () => {
        clearTimeout(limit);
        bot.off("blockUpdate", onBlock);
        bot.off("chat", onChat);
      },
    };
    this.session = session;
    return { anchor, facing };
  }

  stop(): Recording {
    const session = this.session;
    if (session === null) {
      throw new RecordError("not recording");
    }
    session.stop();
    this.session = null;
    return {
      player: session.player,
      facing: session.facing,
      durationMs: Math.round(performance.now() - session.started),
      events: session.events,
      notes: session.notes,
      truncated: session.truncated,
    };
  }

  /** On disconnect: the listeners belong to a bot that is gone. */
  abandon(): void {
    this.session?.stop();
    this.session = null;
  }
}

function cellOf(position: { x: number; y: number; z: number }): Cell {
  return { x: Math.floor(position.x), y: Math.floor(position.y), z: Math.floor(position.z) };
}
