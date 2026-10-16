/**
 * Builds observations: the bot's own state plus what is around it. Grouping and fair-mode
 * filtering are pure functions so they can be tested without a server.
 */
import type { Bot } from "mineflayer";
import { Vec3 } from "vec3";

import type { JsonObject } from "../rpc/json-rpc.js";

/**
 * Fair mode (default for evaluation) reports only blocks the bot could know about: blocks with at
 * least one face open to air. Full mode reports everything in range (AGENTS.md decision 15).
 */
export type Visibility = "fair" | "full";

export const DEFAULT_RADIUS = 16;
export const MAX_RADIUS = 32;
const ENTITY_RADIUS = 32;
const MAX_BLOCK_TYPES = 40;
const MAX_ENTITIES = 30;
// Blocks that never matter to a task and would drown the summary.
const IGNORED_BLOCKS: ReadonlySet<string> = new Set(["air", "cave_air", "void_air"]);
const NEIGHBOURS = [
  [1, 0, 0],
  [-1, 0, 0],
  [0, 1, 0],
  [0, -1, 0],
  [0, 0, 1],
  [0, 0, -1],
] as const;
// Bounds the flood fill: open air above a plain is large, and the fill runs on every observation.
const MAX_OPEN_CELLS = 120_000;

export interface Position {
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

export interface BlockSighting {
  readonly name: string;
  readonly position: Position;
}

const round = (value: number): number => Math.round(value * 100) / 100;

export function distance(a: Position, b: Position): number {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
}

/**
 * Groups sightings by block name: count and nearest position, nearest types first.
 * The LLM gets "oak_log: 14, nearest at (-8, 72, 39), 6.1 blocks", not thousands of coordinates.
 */
export function summarizeBlocks(
  sightings: readonly BlockSighting[],
  origin: Position,
): JsonObject[] {
  const groups = new Map<string, { count: number; nearest: Position; distance: number }>();
  for (const { name, position } of sightings) {
    const d = distance(position, origin);
    const group = groups.get(name);
    if (group === undefined) {
      groups.set(name, { count: 1, nearest: position, distance: d });
    } else {
      group.count += 1;
      if (d < group.distance) {
        group.nearest = position;
        group.distance = d;
      }
    }
  }
  return [...groups.entries()]
    .sort((a, b) => a[1].distance - b[1].distance)
    .slice(0, MAX_BLOCK_TYPES)
    .map(([name, group]) => ({
      name,
      count: group.count,
      nearest: { ...group.nearest },
      distance: round(group.distance),
    }));
}

export const cellKey = (x: number, y: number, z: number): string =>
  `${String(x)},${String(y)},${String(z)}`;

/**
 * The open space (air, water, plants, leaves…) connected to `start`, within `radius`: a flood fill.
 * Fair mode (AGENTS.md decision 15) reports only what touches this space, so ore in a sealed cave
 * or a mob behind a wall stays hidden even though air surrounds it.
 */
export function floodOpenSpace(
  start: Position,
  radius: number,
  isOpen: (x: number, y: number, z: number) => boolean,
  maxCells = MAX_OPEN_CELLS,
): Set<string> {
  const open = new Set<string>();
  if (!isOpen(start.x, start.y, start.z)) {
    return open;
  }
  const queue: Position[] = [start];
  open.add(cellKey(start.x, start.y, start.z));
  for (let head = 0; head < queue.length && open.size < maxCells; head++) {
    const cell = queue[head];
    if (cell === undefined) {
      break;
    }
    for (const [dx, dy, dz] of NEIGHBOURS) {
      const x = cell.x + dx;
      const y = cell.y + dy;
      const z = cell.z + dz;
      const key = cellKey(x, y, z);
      if (open.has(key) || distance({ x, y, z }, start) > radius || !isOpen(x, y, z)) {
        continue;
      }
      open.add(key);
      queue.push({ x, y, z });
    }
  }
  return open;
}

/** A solid block is visible when one of its faces touches the open space. */
export function touchesOpenSpace(position: Position, open: ReadonlySet<string>): boolean {
  return NEIGHBOURS.some(([dx, dy, dz]) =>
    open.has(cellKey(position.x + dx, position.y + dy, position.z + dz)),
  );
}

/** The open space around the bot's eyes, as the game sees it. */
export function visibleSpace(bot: Bot, radius: number): Set<string> {
  const eyes = bot.entity.position.floored().offset(0, 1, 0);
  return floodOpenSpace({ x: eyes.x, y: eyes.y, z: eyes.z }, radius, (x, y, z) => {
    const block = bot.blockAt(new Vec3(x, y, z));
    // Unloaded chunks are not open: nothing is known about them.
    return block !== null && (block.boundingBox === "empty" || block.transparent);
  });
}

export function parseVisibility(value: string | undefined): Visibility {
  if (value === undefined || value === "fair") {
    return "fair";
  }
  if (value === "full") {
    return "full";
  }
  throw new Error(`MC_VISIBILITY=${value} is not valid; use "fair" or "full".`);
}

function nearbyBlocks(bot: Bot, radius: number, visibility: Visibility): JsonObject[] {
  const origin = bot.entity.position;
  const positions = bot.findBlocks({
    matching: (block) => !IGNORED_BLOCKS.has(block.name),
    maxDistance: radius,
    count: 50_000,
  });
  const open = visibility === "fair" ? visibleSpace(bot, radius + 1) : null;
  const sightings: BlockSighting[] = [];
  for (const position of positions) {
    const block = bot.blockAt(position);
    if (block === null) {
      continue;
    }
    if (
      open !== null &&
      !open.has(cellKey(position.x, position.y, position.z)) &&
      !touchesOpenSpace(position, open)
    ) {
      continue;
    }
    sightings.push({ name: block.name, position: { x: position.x, y: position.y, z: position.z } });
  }
  return summarizeBlocks(sightings, origin);
}

function nearbyEntities(bot: Bot, visibility: Visibility): JsonObject[] {
  const origin = bot.entity.position;
  // Fair mode: an entity is seen when the cell it stands in (or its head) is in the open space.
  const open = visibility === "fair" ? visibleSpace(bot, ENTITY_RADIUS) : null;
  const seen = (position: Vec3): boolean => {
    if (open === null) {
      return true;
    }
    const cell = position.floored();
    return (
      open.has(cellKey(cell.x, cell.y, cell.z)) || open.has(cellKey(cell.x, cell.y + 1, cell.z))
    );
  };
  return Object.values(bot.entities)
    .filter(
      (entity) =>
        entity !== bot.entity &&
        entity.position.distanceTo(origin) <= ENTITY_RADIUS &&
        seen(entity.position),
    )
    .map((entity) => {
      const item = entity.name === "item" ? entity.getDroppedItem() : null;
      return {
        name: entity.name ?? entity.type,
        kind: entity.type,
        ...(entity.username === undefined ? {} : { username: entity.username }),
        ...(item === null ? {} : { item: item.name, count: item.count }),
        position: {
          x: round(entity.position.x),
          y: round(entity.position.y),
          z: round(entity.position.z),
        },
        distance: round(entity.position.distanceTo(origin)),
      };
    })
    .sort((a, b) => a.distance - b.distance)
    .slice(0, MAX_ENTITIES);
}

function equipment(bot: Bot): JsonObject {
  // Armor slots 5–8 and the offhand slot 45 in the player inventory window.
  const slot = (index: number): string | null => bot.inventory.slots[index]?.name ?? null;
  return {
    hand: bot.heldItem?.name ?? null,
    head: slot(5),
    chest: slot(6),
    legs: slot(7),
    feet: slot(8),
    offhand: slot(45),
  };
}

/** Parses `observe` params `{ nearby?, radius? }`; the visibility mode is fixed per process. */
export function parseObserveOptions(params: JsonObject, visibility: Visibility): ObserveOptions {
  const { nearby = true, radius = DEFAULT_RADIUS } = params;
  if (typeof nearby !== "boolean") {
    throw new RangeError("observe: `nearby` must be a boolean.");
  }
  if (
    typeof radius !== "number" ||
    !Number.isInteger(radius) ||
    radius < 1 ||
    radius > MAX_RADIUS
  ) {
    throw new RangeError(`observe: \`radius\` must be an integer from 1 to ${String(MAX_RADIUS)}.`);
  }
  return { nearby, radius, visibility };
}

export interface ObserveOptions {
  readonly nearby: boolean;
  readonly radius: number;
  readonly visibility: Visibility;
}

export function buildObservation(bot: Bot, options: ObserveOptions): JsonObject {
  const { x, y, z } = bot.entity.position;
  const below = bot.blockAt(new Vec3(x, y - 0.5, z));
  return {
    username: bot.username,
    // World age in ticks: tells two observations apart and orders them.
    tick: bot.time.age,
    visibility: options.visibility,
    position: { x: round(x), y: round(y), z: round(z) },
    yaw: round(bot.entity.yaw),
    dimension: bot.game.dimension,
    health: bot.health,
    food: bot.food,
    timeOfDay: bot.time.timeOfDay,
    standingOn: below?.name ?? null,
    equipment: equipment(bot),
    // All slots, not items(): items() skips armor, offhand and the crafting grid.
    inventory: bot.inventory.slots.flatMap((item) =>
      item === null ? [] : [{ name: item.name, count: item.count }],
    ),
    ...(options.nearby
      ? {
          nearbyBlocks: nearbyBlocks(bot, options.radius, options.visibility),
          nearbyEntities: nearbyEntities(bot, options.visibility),
        }
      : {}),
  };
}
