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
const MAX_BLOCK_TYPES = 64;
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

export interface OpenSpace {
  /** Keys of the open cells (air, water, plants, leaves…) connected to the start. */
  readonly open: ReadonlySet<string>;
  /** Solid cells that touch the open space: exactly what can be seen from it. */
  readonly boundary: readonly Position[];
  readonly boundaryKeys: ReadonlySet<string>;
  /** True when the cell budget ran out before the radius was covered. */
  readonly truncated: boolean;
}

/**
 * Flood fill of the open space connected to `start`, within `radius`. Fair mode (AGENTS.md
 * decision 15) reports only the solid cells on its boundary, so ore in a sealed cave or a mob
 * behind a wall stays hidden even when air surrounds it. The boundary falls out of the fill for
 * free: it is every neighbour the fill refused because it was not open.
 */
export function floodOpenSpace(
  start: Position,
  radius: number,
  isOpen: (x: number, y: number, z: number) => boolean,
  maxCells = MAX_OPEN_CELLS,
): OpenSpace {
  const open = new Set<string>();
  const boundaryKeys = new Set<string>();
  const boundary: Position[] = [];
  if (!isOpen(start.x, start.y, start.z)) {
    return { open, boundary, boundaryKeys, truncated: false };
  }
  const queue: Position[] = [start];
  open.add(cellKey(start.x, start.y, start.z));
  let head = 0;
  for (; head < queue.length && open.size < maxCells; head++) {
    const cell = queue[head];
    if (cell === undefined) {
      break;
    }
    for (const [dx, dy, dz] of NEIGHBOURS) {
      const x = cell.x + dx;
      const y = cell.y + dy;
      const z = cell.z + dz;
      const key = cellKey(x, y, z);
      if (open.has(key) || boundaryKeys.has(key) || distance({ x, y, z }, start) > radius) {
        continue;
      }
      if (isOpen(x, y, z)) {
        open.add(key);
        queue.push({ x, y, z });
      } else {
        boundaryKeys.add(key);
        boundary.push({ x, y, z });
      }
    }
  }
  return { open, boundary, boundaryKeys, truncated: head < queue.length };
}

/** The open space around the bot's eyes, as the game sees it. */
export function visibleSpace(bot: Bot, radius: number): OpenSpace {
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

interface Nearby {
  readonly blocks: JsonObject[];
  readonly entities: JsonObject[];
  /** Some cells in range were not examined (cell budget); counts are lower bounds. */
  readonly truncated: boolean;
}

function sphereVolume(radius: number): number {
  return Math.ceil((4 / 3) * Math.PI * (radius + 1) ** 3);
}

function nearby(bot: Bot, radius: number, visibility: Visibility): Nearby {
  const origin = bot.entity.position;
  const sightings: BlockSighting[] = [];
  let truncated = false;
  let canSee: (position: Vec3) => boolean = () => true;

  if (visibility === "fair") {
    const space = visibleSpace(bot, radius + 1);
    truncated = space.truncated;
    for (const position of space.boundary) {
      const block = bot.blockAt(new Vec3(position.x, position.y, position.z));
      if (
        block !== null &&
        !IGNORED_BLOCKS.has(block.name) &&
        distance(position, origin) <= radius
      ) {
        sightings.push({ name: block.name, position });
      }
    }
    // An entity is seen when the cell it stands in (or its head) is in the open space.
    canSee = (position) => {
      const cell = position.floored();
      return (
        space.open.has(cellKey(cell.x, cell.y, cell.z)) ||
        space.open.has(cellKey(cell.x, cell.y + 1, cell.z))
      );
    };
  } else {
    // Every block in the sphere can match, so ask for that many: no silent cap.
    const positions = bot.findBlocks({
      matching: (block) => !IGNORED_BLOCKS.has(block.name),
      maxDistance: radius,
      count: sphereVolume(radius),
    });
    for (const position of positions) {
      const block = bot.blockAt(position);
      if (block !== null) {
        sightings.push({
          name: block.name,
          position: { x: position.x, y: position.y, z: position.z },
        });
      }
    }
  }

  const entities = Object.values(bot.entities)
    .filter(
      (entity) =>
        entity !== bot.entity &&
        entity.position.distanceTo(origin) <= radius &&
        canSee(entity.position),
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

  return { blocks: summarizeBlocks(sightings, origin), entities, truncated };
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

function nearbyFields(bot: Bot, options: ObserveOptions): JsonObject {
  const found = nearby(bot, options.radius, options.visibility);
  return {
    nearbyBlocks: found.blocks,
    nearbyEntities: found.entities,
    ...(found.truncated ? { nearbyTruncated: true } : {}),
  };
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
    // All slots but the crafting result (slot 0): items() alone would skip armor, offhand and the
    // crafting grid, while an uncollected craft result is not held yet.
    inventory: bot.inventory.slots.flatMap((item, slot) =>
      item === null || slot === 0 ? [] : [{ name: item.name, count: item.count }],
    ),
    ...(options.nearby ? nearbyFields(bot, options) : {}),
  };
}
