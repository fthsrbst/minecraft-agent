/**
 * Turns a scenario spec (JSON from the evaluator) into server commands. Pure and validated: every
 * value that reaches a command string is checked first, so a spec cannot inject extra commands.
 */
import minecraftData from "minecraft-data";

import { GAME_VERSION } from "../plugin-info.js";
import { ErrorCode, type JsonObject, type JsonValue, RpcError } from "../rpc/json-rpc.js";

const data = minecraftData(GAME_VERSION);

const USERNAME_PATTERN = /^\w{3,16}$/;
const MAX_GIVE_COUNT = 64 * 36; // a full inventory
const WORLD_LIMIT = 30_000_000;
const TIMES = { day: 1000, noon: 6000, night: 13000, midnight: 18000 } as const;
const WEATHERS = ["clear", "rain", "thunder"] as const;
// Removed on reset so leftovers from an earlier run cannot satisfy a later predicate.
const RESET_RADIUS = 64;
// The server refuses larger fills; also a sane bound for a test arena.
const MAX_FILL_VOLUME = 32_768;
const MAX_LIST = 64;
const MAX_SUMMONS = 20;
// Entities a scenario creates carry this tag, so reset can remove exactly them.
export const SCENARIO_TAG = "scenario";
const Y_MIN = -64;
const Y_MAX = 320;

interface BlockPosition {
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

/** Plain decimal notation: the server rejects exponent forms such as 1e-7. */
function coordinate(value: number): string {
  return value.toFixed(6).replace(/\.?0+$/, "");
}

function invalid(message: string): RpcError {
  return new RpcError(ErrorCode.InvalidParams, `scenario: ${message}`);
}

function isObject(value: JsonValue | undefined): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finiteNumber(value: JsonValue | undefined, name: string, limit: number): number {
  if (typeof value !== "number" || !Number.isFinite(value) || Math.abs(value) > limit) {
    throw invalid(`\`${name}\` must be a number within ±${String(limit)}.`);
  }
  return value;
}

function list(value: JsonValue | undefined, name: string, max: number): JsonObject[] {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value) || value.length > max) {
    throw invalid(`\`${name}\` must be a list of at most ${String(max)} objects.`);
  }
  return value.map((entry) => {
    if (!isObject(entry)) {
      throw invalid(`each \`${name}\` entry must be an object.`);
    }
    return entry;
  });
}

function blockPosition(value: JsonValue | undefined, name: string): BlockPosition {
  if (!isObject(value)) {
    throw invalid(`\`${name}\` must be { x, y, z }.`);
  }
  const axis = (key: "x" | "y" | "z", limit: number, min = -limit): number => {
    const n = value[key];
    if (typeof n !== "number" || !Number.isInteger(n) || n < min || n > limit) {
      throw invalid(`\`${name}.${key}\` must be an integer block coordinate.`);
    }
    return n;
  };
  return { x: axis("x", WORLD_LIMIT), y: axis("y", Y_MAX, Y_MIN), z: axis("z", WORLD_LIMIT) };
}

function blockName(value: JsonValue | undefined): string {
  if (typeof value !== "string" || !Object.hasOwn(data.blocksByName, value)) {
    throw invalid(`unknown block ${JSON.stringify(value ?? null)} for ${GAME_VERSION}.`);
  }
  return value;
}

const at = ({ x, y, z }: BlockPosition): string => `${String(x)} ${String(y)} ${String(z)}`;

function placeCommands(value: JsonValue | undefined): string[] {
  return list(value, "place", MAX_LIST).map(
    (entry) => `setblock ${at(blockPosition(entry, "place"))} minecraft:${blockName(entry.block)}`,
  );
}

function fillCommands(value: JsonValue | undefined): string[] {
  return list(value, "fill", MAX_LIST).map((entry) => {
    const from = blockPosition(entry.from, "fill.from");
    const to = blockPosition(entry.to, "fill.to");
    const volume =
      (Math.abs(to.x - from.x) + 1) * (Math.abs(to.y - from.y) + 1) * (Math.abs(to.z - from.z) + 1);
    if (volume > MAX_FILL_VOLUME) {
      throw invalid(`fill volume ${String(volume)} is over ${String(MAX_FILL_VOLUME)} blocks.`);
    }
    return `fill ${at(from)} ${at(to)} minecraft:${blockName(entry.block)}`;
  });
}

const MAX_OFFSET = 32;

function summonCommands(player: string, value: JsonValue | undefined): string[] {
  return list(value, "summon", MAX_SUMMONS).map((entry) => {
    const { entity } = entry;
    if (
      typeof entity !== "string" ||
      entity === "player" ||
      !Object.hasOwn(data.entitiesByName, entity)
    ) {
      throw invalid(`unknown entity ${JSON.stringify(entity ?? null)} for ${GAME_VERSION}.`);
    }
    const tags = `{Tags:["${SCENARIO_TAG}"]}`;
    if (entry.offset !== undefined) {
      // Relative to the player, wherever the bot is at that moment (e.g. during a running skill).
      const offset = entry.offset;
      if (!isObject(offset)) {
        throw invalid("`summon.offset` must be { x, y, z }.");
      }
      const d = (key: "x" | "y" | "z"): string =>
        String(finiteNumber(offset[key], `summon.offset.${key}`, MAX_OFFSET));
      return `execute at ${player} run summon minecraft:${entity} ~${d("x")} ~${d("y")} ~${d("z")} ${tags}`;
    }
    const position = blockPosition(entry, "summon");
    return `summon minecraft:${entity} ${at(position)} ${tags}`;
  });
}

export function parsePlayer(value: JsonValue | undefined): string {
  if (typeof value !== "string" || !USERNAME_PATTERN.test(value)) {
    throw invalid("`player` must be a Minecraft username (3–16 letters, digits or _).");
  }
  return value;
}

function giveCommands(player: string, value: JsonValue | undefined): string[] {
  if (value === undefined) {
    return [];
  }
  if (!Array.isArray(value)) {
    throw invalid("`give` must be a list of { item, count }.");
  }
  return value.map((entry) => {
    if (!isObject(entry)) {
      throw invalid("each `give` entry must be an object.");
    }
    const { item, count = 1 } = entry;
    // Object.hasOwn, not `in`: `in` also accepts inherited names such as "constructor".
    if (typeof item !== "string" || item === "air" || !Object.hasOwn(data.itemsByName, item)) {
      throw invalid(`unknown item ${JSON.stringify(item ?? null)} for ${GAME_VERSION}.`);
    }
    if (
      typeof count !== "number" ||
      !Number.isInteger(count) ||
      count < 1 ||
      count > MAX_GIVE_COUNT
    ) {
      throw invalid(
        `\`count\` for ${item} must be an integer from 1 to ${String(MAX_GIVE_COUNT)}.`,
      );
    }
    return `give ${player} minecraft:${item} ${String(count)}`;
  });
}

function teleportCommand(player: string, value: JsonValue | undefined): string[] {
  if (value === undefined) {
    return [];
  }
  if (!isObject(value)) {
    throw invalid("`teleport` must be { x, y, z }.");
  }
  const x = finiteNumber(value.x, "teleport.x", WORLD_LIMIT);
  const y = finiteNumber(value.y, "teleport.y", 320);
  const z = finiteNumber(value.z, "teleport.z", WORLD_LIMIT);
  return [`tp ${player} ${coordinate(x)} ${coordinate(y)} ${coordinate(z)}`];
}

function timeCommand(value: JsonValue | undefined): string[] {
  if (value === undefined) {
    return [];
  }
  if (typeof value === "string" && Object.hasOwn(TIMES, value)) {
    return [`time set ${String(TIMES[value as keyof typeof TIMES])}`];
  }
  if (typeof value === "number" && Number.isInteger(value) && value >= 0 && value < 24000) {
    return [`time set ${String(value)}`];
  }
  throw invalid(
    `\`time\` must be one of ${Object.keys(TIMES).join(", ")} or a tick from 0 to 23999.`,
  );
}

function weatherCommand(value: JsonValue | undefined): string[] {
  if (value === undefined) {
    return [];
  }
  if (typeof value !== "string" || !(WEATHERS as readonly string[]).includes(value)) {
    throw invalid(`\`weather\` must be one of ${WEATHERS.join(", ")}.`);
  }
  return [`weather ${value}`];
}

/**
 * Setup spec: `{ clear?, fill?, place?, teleport?, give?, summon?, time?, weather? }`.
 * Terrain first (fill, then single blocks), then the player, then entities: the bot must not be
 * teleported into a block that the fill is about to create.
 */
export function setupCommands(player: string, spec: JsonObject): string[] {
  const known = new Set([
    "clear",
    "fill",
    "place",
    "teleport",
    "give",
    "summon",
    "time",
    "weather",
  ]);
  const unknown = Object.keys(spec).filter((key) => !known.has(key));
  if (unknown.length > 0) {
    throw invalid(`unknown setup field(s): ${unknown.join(", ")}.`);
  }
  if (spec.clear !== undefined && typeof spec.clear !== "boolean") {
    throw invalid("`clear` must be a boolean.");
  }
  return [
    ...(spec.clear === true ? [`clear ${player}`] : []),
    ...fillCommands(spec.fill),
    ...placeCommands(spec.place),
    ...teleportCommand(player, spec.teleport),
    ...giveCommands(player, spec.give),
    ...summonCommands(player, spec.summon),
    ...timeCommand(spec.time),
    ...weatherCommand(spec.weather),
  ];
}

/**
 * Brings the player back to a neutral state: empty inventory, full health and food, day, no drops,
 * no scenario mobs, and (if given) back at a spawn point so position predicates start false.
 * Terrain is not restored here; a fresh world per seed does that (`scenario.world`).
 */
export function resetCommands(player: string, spawn?: JsonValue): string[] {
  return [
    ...(spawn === undefined ? [] : teleportCommand(player, spawn)),
    `kill @e[tag=${SCENARIO_TAG}]`,
    `clear ${player}`,
    `effect clear ${player}`,
    `gamemode survival ${player}`,
    `effect give ${player} minecraft:instant_health 1 4 true`,
    `effect give ${player} minecraft:saturation 1 20 true`,
    `execute at ${player} run kill @e[type=minecraft:item,distance=..${String(RESET_RADIUS)}]`,
    "time set 1000",
    "weather clear",
  ];
}

// Replay arenas (P4.1): far from spawn and from each other, high enough to avoid any terrain.
const ARENA_START = 2_000;
const ARENA_SPACING = 48;
const ARENA_FLOOR_Y = 99;
const ARENA_RADIUS = 8;
const ARENA_HEIGHT = 9;
const MAX_ARENAS = 1_000;
// Minecraft's /tp yaw (degrees): 0 looks south, 90 west, 180 north, -90 east.
const ARENA_YAW: Readonly<Record<string, number>> = { south: 0, west: 90, north: 180, east: -90 };

export interface Arena {
  /** Loads the arena's chunks: nobody stands there yet, and `fill` refuses unloaded chunks. */
  readonly load: string[];
  readonly commands: string[];
  readonly origin: BlockPosition;
  readonly facing: string;
}

/**
 * A fresh, flat, empty spot for replaying a demonstrated build: a stone floor with open air above,
 * the player in the middle facing `facing`, holding exactly `give`. Each `index` is its own spot,
 * so an earlier replay can never satisfy a later check.
 */
export function arenaCommands(
  player: string,
  index: JsonValue | undefined,
  facing: JsonValue | undefined,
  give: JsonValue | undefined,
): Arena {
  if (typeof index !== "number" || !Number.isInteger(index) || index < 0 || index >= MAX_ARENAS) {
    throw invalid(`\`index\` must be an integer from 0 to ${String(MAX_ARENAS - 1)}.`);
  }
  // By default the replays turn through all four directions, so a build is checked turned.
  const turn = facing ?? (["north", "east", "south", "west"] as const)[index % 4];
  if (typeof turn !== "string" || !Object.hasOwn(ARENA_YAW, turn)) {
    throw invalid("`facing` must be north, east, south or west.");
  }
  const cx = ARENA_START + index * ARENA_SPACING;
  const cz = ARENA_START;
  const y = ARENA_FLOOR_Y;
  const r = ARENA_RADIUS;
  const area = (dy0: number, dy1: number, block: string): string =>
    `fill ${String(cx - r)} ${String(y + dy0)} ${String(cz - r)} ${String(cx + r)} ${String(y + dy1)} ${String(cz + r)} minecraft:${block}`;
  return {
    // An earlier arena no longer needs to stay loaded; the player keeps their own chunks loaded.
    load: [
      "forceload remove all",
      `forceload add ${String(cx - r)} ${String(cz - r)} ${String(cx + r)} ${String(cz + r)}`,
    ],
    commands: [
      `clear ${player}`,
      area(0, 0, "stone"),
      area(1, ARENA_HEIGHT, "air"),
      `tp ${player} ${String(cx)}.5 ${String(y + 1)} ${String(cz)}.5 ${String(ARENA_YAW[turn] ?? 0)} 0`,
      ...giveCommands(player, give),
    ],
    origin: { x: cx, y: y + 1, z: cz },
    facing: turn,
  };
}

// Replies that mean the command did not do what was asked. Minecraft answers over RCON with text,
// not status codes, so these are matched on the message.
const FAILURE_REPLIES = [
  "No player was found",
  "Unknown or incomplete command",
  "Incorrect argument",
  "Unknown item",
  "Expected ",
  "Invalid ",
  "Could not ",
  "No entity was found",
  "not loaded",
];

/** Removing entities that are already gone is the goal of a kill, not a failure. */
const NOTHING_TO_KILL = "No entity was found";

export function isFailureReply(reply: string, command = ""): boolean {
  const isKill = command.startsWith("kill ") || command.includes(" run kill ");
  if (isKill && reply.includes(NOTHING_TO_KILL)) {
    return false;
  }
  return FAILURE_REPLIES.some((marker) => reply.includes(marker));
}
