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
    if (typeof item !== "string" || !Object.hasOwn(data.itemsByName, item)) {
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
  return [`tp ${player} ${String(x)} ${String(y)} ${String(z)}`];
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
 * Setup spec: `{ clear?, give?: [{ item, count }], teleport?: { x, y, z }, time?, weather? }`.
 * `clear` empties the inventory first so the scenario starts from a known state.
 */
export function setupCommands(player: string, spec: JsonObject): string[] {
  const known = new Set(["clear", "give", "teleport", "time", "weather"]);
  const unknown = Object.keys(spec).filter((key) => !known.has(key));
  if (unknown.length > 0) {
    throw invalid(`unknown setup field(s): ${unknown.join(", ")}.`);
  }
  if (spec.clear !== undefined && typeof spec.clear !== "boolean") {
    throw invalid("`clear` must be a boolean.");
  }
  return [
    ...(spec.clear === true ? [`clear ${player}`] : []),
    ...teleportCommand(player, spec.teleport),
    ...giveCommands(player, spec.give),
    ...timeCommand(spec.time),
    ...weatherCommand(spec.weather),
  ];
}

/** Brings the player back to a neutral state: empty inventory, full health and food, day, no drops. */
export function resetCommands(player: string): string[] {
  return [
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
];

export function isFailureReply(reply: string): boolean {
  return FAILURE_REPLIES.some((marker) => reply.includes(marker));
}
