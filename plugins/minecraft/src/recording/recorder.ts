/**
 * Watches a demonstrator from the bot's side (the thin v1 of research.md §4.5: a watcher, not the
 * recording proxy). It sees block changes near the demonstrator and their `//` chat notes; it
 * cannot see their inventory or crafting. Changes are *observed* world changes, not the player's
 * requests: a change is attributed to the demonstrator only if it happens within their reach, away
 * from the bot's own work, and inside a bounded area around where they started.
 */
import type { Block } from "prismarine-block";

import { type BlockEvent, type Note, type Recording } from "./blueprint.js";
import { type Cell, type Facing, facingFromYaw, toRelative } from "./frame.js";

// A player reaches about 4.5 blocks from the eyes; a little more covers the feet-to-block distance.
const REACH = 6;
// v1 builds are small: changes farther than this from the start are not part of the demonstration.
export const MAX_SPAN = 16;
const MAX_EVENTS = 2_000;
const MAX_NOTES = 50;
const MAX_NOTE_LENGTH = 200;
export const MAX_RECORDING_MS = 10 * 60_000;
export const NOTE_PREFIX = "//";

export class RecordError extends Error {}

interface Position {
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

/** The part of a Mineflayer bot the recorder uses, so it can be tested without a server. */
export interface WatchedWorld {
  readonly players: Readonly<
    Record<string, { readonly entity?: { readonly position: Position; readonly yaw: number } }>
  >;
  on(event: "blockUpdate", listener: (before: Block | null, after: Block) => void): unknown;
  on(event: "chat", listener: (sender: string, message: string) => void): unknown;
  off(event: "blockUpdate", listener: (before: Block | null, after: Block) => void): unknown;
  off(event: "chat", listener: (sender: string, message: string) => void): unknown;
}

export interface RecorderHooks {
  /** True while the bot itself changes blocks (a skill or an action): those are not the demo. */
  readonly botBusy: () => boolean;
  /** The recording ended on its own (time limit); the core must learn that it is over. */
  readonly ended: (player: string, reason: string) => void;
}

class Session {
  readonly started = performance.now();
  readonly events: BlockEvent[] = [];
  readonly notes: Note[] = [];
  truncated = false;
  private readonly limit: NodeJS.Timeout;

  constructor(
    private readonly world: WatchedWorld,
    private readonly hooks: RecorderHooks,
    readonly player: string,
    readonly anchor: Cell,
    readonly facing: Facing,
    onTimeLimit: () => void,
  ) {
    world.on("blockUpdate", this.onBlock);
    world.on("chat", this.onChat);
    this.limit = setTimeout(onTimeLimit, MAX_RECORDING_MS);
  }

  private elapsed(): number {
    return Math.round(performance.now() - this.started);
  }

  private readonly onBlock = (before: Block | null, after: Block): void => {
    const demonstrator = this.world.players[this.player]?.entity;
    // An unknown old block (unloaded chunk) cannot be a change we can reason about.
    if (this.truncated || demonstrator === undefined || before === null) {
      return;
    }
    if (before.name === after.name || this.hooks.botBusy()) {
      return;
    }
    const cell = cellOf(after.position);
    const center = { x: cell.x + 0.5, y: cell.y + 0.5, z: cell.z + 0.5 };
    if (distance(center, demonstrator.position) > REACH) {
      return;
    }
    const relative = toRelative(cell, this.anchor, this.facing);
    if (Math.max(Math.abs(relative.a), Math.abs(relative.b), Math.abs(relative.c)) > MAX_SPAN) {
      return;
    }
    if (this.events.length >= MAX_EVENTS) {
      this.truncated = true;
      return;
    }
    this.events.push({ ...relative, t: this.elapsed(), from: before.name, to: after.name });
  };

  private readonly onChat = (sender: string, message: string): void => {
    if (sender !== this.player || !message.startsWith(NOTE_PREFIX)) {
      return;
    }
    const text = message.slice(NOTE_PREFIX.length).trim().slice(0, MAX_NOTE_LENGTH);
    if (text.length > 0 && this.notes.length < MAX_NOTES) {
      this.notes.push({ t: this.elapsed(), text });
    }
  };

  close(): Recording {
    clearTimeout(this.limit);
    this.world.off("blockUpdate", this.onBlock);
    this.world.off("chat", this.onChat);
    return {
      player: this.player,
      facing: this.facing,
      durationMs: this.elapsed(),
      events: this.events,
      notes: this.notes,
      truncated: this.truncated,
    };
  }
}

export class Recorder {
  private session: Session | null = null;
  // A recording that ended on its own is kept until the core asks for it with `stop`.
  private finished: Recording | null = null;

  constructor(
    private readonly getWorld: () => WatchedWorld,
    private readonly hooks: RecorderHooks,
  ) {}

  get recording(): string | null {
    return this.session?.player ?? null;
  }

  start(player: string): { anchor: Cell; facing: Facing } {
    if (this.session !== null) {
      throw new RecordError(`already recording ${this.session.player}; stop that first`);
    }
    const world = this.getWorld();
    const entity = world.players[player]?.entity;
    if (entity === undefined) {
      throw new RecordError(`cannot see ${player}; come closer so the bot can watch`);
    }
    const anchor = cellOf(entity.position);
    const facing = facingFromYaw(entity.yaw);
    this.finished = null;
    this.session = new Session(world, this.hooks, player, anchor, facing, () => {
      this.finishOnItsOwn("the 10 minute limit was reached");
    });
    return { anchor, facing };
  }

  stop(): Recording {
    if (this.session !== null) {
      const recording = this.session.close();
      this.session = null;
      return recording;
    }
    if (this.finished !== null) {
      const recording = this.finished;
      this.finished = null;
      return recording;
    }
    throw new RecordError("not recording");
  }

  /** On disconnect: the listeners belong to a bot that is gone; what was seen is kept. */
  abandon(): void {
    if (this.session !== null) {
      this.finishOnItsOwn("the bot disconnected");
    }
  }

  private finishOnItsOwn(reason: string): void {
    const session = this.session;
    if (session === null) {
      return;
    }
    this.finished = { ...session.close(), truncated: true };
    this.session = null;
    this.hooks.ended(session.player, reason);
  }
}

function cellOf(position: Position): Cell {
  return { x: Math.floor(position.x), y: Math.floor(position.y), z: Math.floor(position.z) };
}

function distance(p: Position, q: Position): number {
  return Math.hypot(p.x - q.x, p.y - q.y, p.z - q.z);
}
