/**
 * The game actions a skill may request through the broker. Arguments arrive from untrusted skill
 * code, so each primitive validates them first; each one stops when the run is aborted (timeout or
 * cancel) and has its own time limit, so a skill can never leave the bot walking forever.
 */
import type { Bot } from "mineflayer";
// Type-only import: adds `bot.collectBlock` to Mineflayer's Bot type (the plugin is loaded at spawn).
import type {} from "mineflayer-collectblock";
import pathfinderModule from "mineflayer-pathfinder";
import { Vec3 } from "vec3";

import { parseAction } from "../bridge/actions.js";
import { buildObservation, parseObserveOptions, type Visibility } from "../bridge/observation.js";
import type { JsonObject, JsonValue } from "../rpc/json-rpc.js";
import type { Primitive } from "./broker.js";

const { goals } = pathfinderModule;

const GOTO_TIMEOUT_MS = 60_000;
const COLLECT_TIMEOUT_MS = 120_000;
const SEARCH_RADIUS = 64;
const TABLE_RADIUS = 32;
const MAX_COLLECT = 64;
const MAX_CRAFT = 64;
const MAX_WAIT_MS = 10_000;
// The pathfinder reports "stuck" when the bot does not progress; a few in a row means give up.
const MAX_STUCK = 4;

export class PrimitiveError extends Error {
  override readonly name = "PrimitiveError";
}

// --- argument validation (pure) ----------------------------------------------------------------

export function requireInt(
  args: JsonObject,
  key: string,
  min: number,
  max: number,
  fallback?: number,
): number {
  const value = args[key] ?? fallback;
  if (typeof value !== "number" || !Number.isInteger(value) || value < min || value > max) {
    throw new PrimitiveError(
      `\`${key}\` must be an integer from ${String(min)} to ${String(max)}.`,
    );
  }
  return value;
}

export function requireCoordinate(args: JsonObject, key: "x" | "y" | "z"): number {
  const value = args[key];
  if (typeof value !== "number" || !Number.isFinite(value) || Math.abs(value) > 30_000_000) {
    throw new PrimitiveError(`\`${key}\` must be a finite coordinate.`);
  }
  return value;
}

export function requireName(
  args: JsonObject,
  key: string,
  known: Readonly<Record<string, unknown>>,
): string {
  const value = args[key];
  if (typeof value !== "string" || !Object.hasOwn(known, value)) {
    throw new PrimitiveError(`unknown ${key} ${JSON.stringify(value ?? null)}.`);
  }
  return value;
}

// --- helpers -----------------------------------------------------------------------------------

function throwIfAborted(signal: AbortSignal): void {
  if (signal.aborted) {
    throw new PrimitiveError("the skill run was stopped");
  }
}

/** Runs `task` until it settles, the run is aborted, or `timeoutMs` passes; `stop` cleans up. */
async function bounded<T>(
  task: Promise<T>,
  signal: AbortSignal,
  timeoutMs: number,
  what: string,
  stop: () => void,
): Promise<T> {
  throwIfAborted(signal);
  let timer: NodeJS.Timeout | undefined;
  let onAbort: (() => void) | undefined;
  const limits = new Promise<never>((_, reject) => {
    timer = setTimeout(() => {
      reject(new PrimitiveError(`${what} took longer than ${String(timeoutMs / 1000)} s`));
    }, timeoutMs);
    onAbort = () => {
      reject(new PrimitiveError("the skill run was stopped"));
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
  try {
    return await Promise.race([task, limits]);
  } catch (error) {
    stop();
    throw error;
  } finally {
    clearTimeout(timer);
    if (onAbort !== undefined) {
      signal.removeEventListener("abort", onAbort);
    }
  }
}

function inventoryCounts(bot: Bot): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of bot.inventory.items()) {
    counts[item.name] = (counts[item.name] ?? 0) + item.count;
  }
  return counts;
}

function gained(before: Record<string, number>, after: Record<string, number>): JsonObject {
  const delta: JsonObject = {};
  for (const [name, count] of Object.entries(after)) {
    const diff = count - (before[name] ?? 0);
    if (diff > 0) {
      delta[name] = diff;
    }
  }
  return delta;
}

const position = (bot: Bot): JsonObject => {
  const { x, y, z } = bot.entity.position;
  return {
    x: Math.round(x * 100) / 100,
    y: Math.round(y * 100) / 100,
    z: Math.round(z * 100) / 100,
  };
};

async function goNear(
  bot: Bot,
  target: Vec3,
  range: number,
  signal: AbortSignal,
  timeoutMs: number,
): Promise<void> {
  let stuck = 0;
  const onReset = (reason: string): void => {
    if (reason === "stuck" && ++stuck >= MAX_STUCK) {
      bot.pathfinder.stop();
    }
  };
  bot.on("path_reset", onReset);
  try {
    await bounded(
      bot.pathfinder.goto(new goals.GoalNear(target.x, target.y, target.z, range)),
      signal,
      timeoutMs,
      "goTo",
      () => {
        bot.pathfinder.stop();
      },
    );
  } catch (error) {
    if (stuck >= MAX_STUCK) {
      const { x, z } = bot.entity.position;
      throw new PrimitiveError(
        `goTo got stuck ${String(stuck)} times near ${x.toFixed(1)}, ${z.toFixed(1)}`,
      );
    }
    throw error;
  } finally {
    bot.removeListener("path_reset", onReset);
  }
}

// Placing a block on these replaces them, as a player would.
export const REPLACEABLE: ReadonlySet<string> = new Set([
  "air",
  "cave_air",
  "short_grass",
  "tall_grass",
  "fern",
  "large_fern",
  "leaf_litter",
  "dead_bush",
  "snow",
]);

/** Free (air or a plant) above a full solid block, and not where the bot itself stands. */
function canPlaceAt(bot: Bot, target: Vec3): boolean {
  const feet = bot.entity.position.floored();
  if (
    target.x === feet.x &&
    target.z === feet.z &&
    (target.y === feet.y || target.y === feet.y + 1)
  ) {
    return false;
  }
  const here = bot.blockAt(target);
  const below = bot.blockAt(target.offset(0, -1, 0));
  return here !== null && REPLACEABLE.has(here.name) && below?.boundingBox === "block";
}

function findPlaceSpot(bot: Bot): Vec3 | null {
  const feet = bot.entity.position.floored();
  const spots: Vec3[] = [];
  for (let dx = -3; dx <= 3; dx++) {
    for (let dz = -3; dz <= 3; dz++) {
      for (const dy of [0, -1, 1]) {
        spots.push(feet.offset(dx, dy, dz));
      }
    }
  }
  spots.sort((a, b) => a.distanceTo(feet) - b.distanceTo(feet));
  return spots.find((spot) => canPlaceAt(bot, spot)) ?? null;
}

// --- primitives --------------------------------------------------------------------------------

export function createPrimitives(
  getBot: () => Bot,
  visibility: Visibility,
): ReadonlyMap<string, Primitive> {
  const registry = () => getBot().registry;

  const goTo: Primitive = async (args, signal) => {
    const bot = getBot();
    const target = new Vec3(
      requireCoordinate(args, "x"),
      requireCoordinate(args, "y"),
      requireCoordinate(args, "z"),
    );
    const range = requireInt(args, "range", 0, 16, 1);
    const timeoutMs = requireInt(args, "timeoutMs", 1_000, GOTO_TIMEOUT_MS, GOTO_TIMEOUT_MS);
    await goNear(bot, target, range, signal, timeoutMs);
    return { ok: true, position: position(bot) };
  };

  const collect: Primitive = async (args, signal) => {
    const bot = getBot();
    const block = requireName(args, "block", registry().blocksByName);
    const count = requireInt(args, "count", 1, MAX_COLLECT, 1);
    const timeoutMs = requireInt(args, "timeoutMs", 1_000, COLLECT_TIMEOUT_MS, COLLECT_TIMEOUT_MS);
    const blockId = registry().blocksByName[block]?.id;
    const targets = bot
      .findBlocks({ matching: blockId ?? -1, maxDistance: SEARCH_RADIUS, count })
      .flatMap((pos) => {
        const found = bot.blockAt(pos);
        return found === null ? [] : [found];
      });
    if (targets.length === 0) {
      throw new PrimitiveError(`no ${block} within ${String(SEARCH_RADIUS)} blocks`);
    }
    const before = inventoryCounts(bot);
    await bounded(
      bot.collectBlock.collect(targets, { ignoreNoPath: true }),
      signal,
      timeoutMs,
      "collect",
      () => {
        bot.collectBlock.cancelTask().catch(() => undefined);
        bot.pathfinder.stop();
      },
    );
    return {
      ok: true,
      requested: count,
      found: targets.length,
      gained: gained(before, inventoryCounts(bot)),
    };
  };

  const craft: Primitive = async (args, signal) => {
    const bot = getBot();
    const item = requireName(args, "item", registry().itemsByName);
    const count = requireInt(args, "count", 1, MAX_CRAFT, 1);
    const itemId = registry().itemsByName[item]?.id ?? -1;
    // Recipes that fit the 2×2 inventory grid need no table; the rest need one nearby.
    let table = null;
    let recipe = bot.recipesFor(itemId, null, 1, null)[0];
    if (recipe === undefined) {
      const tableId = registry().blocksByName.crafting_table?.id ?? -1;
      table = bot.findBlock({ matching: tableId, maxDistance: TABLE_RADIUS });
      if (table === null) {
        throw new PrimitiveError(
          `cannot craft ${item}: missing ingredients, or it needs a crafting_table within ${String(TABLE_RADIUS)} blocks`,
        );
      }
      recipe = bot.recipesFor(itemId, null, 1, table)[0];
      if (recipe === undefined) {
        throw new PrimitiveError(`cannot craft ${item}: missing ingredients`);
      }
      if (table.position.distanceTo(bot.entity.position) > 4) {
        await goNear(bot, table.position, 2, signal, GOTO_TIMEOUT_MS);
      }
    }
    // `count` is the number of items wanted; one craft may yield several (e.g. 4 planks).
    const times = Math.ceil(count / recipe.result.count);
    const before = inventoryCounts(bot);
    await bounded(
      bot.craft(recipe, times, table ?? undefined),
      signal,
      30_000,
      "craft",
      () => undefined,
    );
    return { ok: true, gained: gained(before, inventoryCounts(bot)) };
  };

  const equip: Primitive = async (args, signal) => {
    const bot = getBot();
    const item = requireName(args, "item", registry().itemsByName);
    const held = bot.inventory.items().find((stack) => stack.name === item);
    if (held === undefined) {
      throw new PrimitiveError(`no ${item} in the inventory`);
    }
    await bounded(bot.equip(held, "hand"), signal, 5_000, "equip", () => undefined);
    return { ok: true, hand: item };
  };

  const place: Primitive = async (args, signal) => {
    const bot = getBot();
    const item = requireName(args, "item", registry().itemsByName);
    const stack = bot.inventory.items().find((s) => s.name === item);
    if (stack === undefined) {
      throw new PrimitiveError(`no ${item} in the inventory`);
    }
    let target: Vec3;
    if (args.x === undefined && args.y === undefined && args.z === undefined) {
      // No position given: the nearest spot on solid ground next to the bot.
      const free = findPlaceSpot(bot);
      if (free === null) {
        throw new PrimitiveError("no free spot on solid ground within 3 blocks of the bot");
      }
      target = free;
    } else {
      target = new Vec3(
        requireCoordinate(args, "x"),
        requireCoordinate(args, "y"),
        requireCoordinate(args, "z"),
      ).floored();
    }
    const below = bot.blockAt(target.offset(0, -1, 0));
    if (below === null || !canPlaceAt(bot, target)) {
      throw new PrimitiveError(
        `cannot place at ${target.toString()}: it must be free (air or plants) above a solid block`,
      );
    }
    if (target.distanceTo(bot.entity.position) > 4.5) {
      await goNear(bot, target, 3, signal, GOTO_TIMEOUT_MS);
    }
    await bounded(bot.equip(stack, "hand"), signal, 5_000, "equip", () => undefined);
    await bounded(
      bot.placeBlock(below, new Vec3(0, 1, 0)),
      signal,
      5_000,
      "place",
      () => undefined,
    );
    return { ok: true, item, position: { x: target.x, y: target.y, z: target.z } };
  };

  const observe: Primitive = (args) =>
    Promise.resolve(buildObservation(getBot(), parseObserveOptions(args, visibility)));

  const chat: Primitive = (args) => {
    const action = parseAction({ primitive: "chat", args });
    if (action.primitive === "chat") {
      getBot().chat(action.text);
    }
    return Promise.resolve({ ok: true });
  };

  const wait: Primitive = (args, signal) => {
    const ms = requireInt(args, "ms", 1, MAX_WAIT_MS);
    return bounded(
      new Promise<JsonValue>((resolve) =>
        setTimeout(() => {
          resolve({ ok: true });
        }, ms),
      ),
      signal,
      ms + 1_000,
      "wait",
      () => undefined,
    );
  };

  return new Map([
    ["goTo", goTo],
    ["collect", collect],
    ["craft", craft],
    ["equip", equip],
    ["place", place],
    ["observe", observe],
    ["chat", chat],
    ["wait", wait],
  ]);
}

/** The skill API as the LLM sees it (P2.4 puts this into the prompt). */
export const SKILL_API: JsonObject[] = [
  {
    name: "bot.observe(options?)",
    returns: "observation",
    description: "Current state; options { nearby?: boolean, radius?: 1..32 }.",
  },
  {
    name: "bot.goTo(x, y, z, options?)",
    returns: "{ ok, position }",
    description:
      "Pathfind near a point; options { range?: 0..16 (default 1), timeoutMs? }. Throws when stuck.",
  },
  {
    name: "bot.collect(block, count?)",
    returns: "{ ok, requested, found, gained }",
    description:
      "Find, mine and pick up up to count (≤ 64) blocks of a type within 64 blocks; uses the best tool.",
  },
  {
    name: "bot.craft(item, count?)",
    returns: "{ ok, gained }",
    description:
      "Craft at least count items; uses a crafting_table within 32 blocks when the recipe needs one.",
  },
  {
    name: "bot.place(item, position?)",
    returns: "{ ok, item, position }",
    description:
      "Place a block from the inventory at {x, y, z} (air above a solid block), or next to the bot.",
  },
  {
    name: "bot.equip(item)",
    returns: "{ ok, hand }",
    description: "Hold an item from the inventory.",
  },
  { name: "bot.chat(text)", returns: "{ ok }", description: "Say a line in chat; no commands." },
  { name: "bot.wait(ms)", returns: "{ ok }", description: "Wait up to 10 000 ms." },
  { name: "log(...values)", returns: "undefined", description: "Write a line to the run's log." },
];
