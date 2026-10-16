/**
 * The acceptance check for a demonstrated build, independent of the skill code that built it
 * (decision 6): it reads the world, not the skill's report. Unloaded cells are "unknown", never a
 * match.
 */
import type { Bot } from "mineflayer";
import { Vec3 } from "vec3";

import type { JsonObject, JsonValue } from "../rpc/json-rpc.js";
import type { Blueprint, PlaceStep } from "./blueprint.js";
import { type Cell, type Facing, isFacing, type RelativeCell, toWorld } from "./frame.js";

const MAX_CELLS = 4_096;
const MAX_MISSING_REPORTED = 10;
const EMPTY: ReadonlySet<string> = new Set(["air", "cave_air", "void_air"]);

export class CheckInputError extends Error {}

/**
 * Only placed blocks count toward `total`/`matched`: a fresh replay spot is already empty, so a
 * cell to clear would match without the skill doing anything. Cleared cells are reported apart.
 */
export interface StructureCheck {
  readonly total: number;
  readonly matched: number;
  readonly unknown: number;
  readonly cleared: number;
  readonly clearTotal: number;
  readonly missing: readonly JsonObject[];
}

export function checkStructure(
  bot: Pick<Bot, "blockAt">,
  blueprint: Blueprint,
  origin: Cell,
  facing: Facing,
): StructureCheck {
  let matched = 0;
  let unknown = 0;
  const missing: JsonObject[] = [];
  const nameAt = (cell: RelativeCell): { p: Cell; name: string | undefined } => {
    const p = toWorld(cell, origin, facing);
    return { p, name: bot.blockAt(new Vec3(p.x, p.y, p.z))?.name };
  };
  for (const step of blueprint.place) {
    const { p, name } = nameAt(step);
    if (name === undefined) {
      unknown += 1;
    } else if (name === step.block) {
      matched += 1;
    } else if (missing.length < MAX_MISSING_REPORTED) {
      missing.push({ ...p, want: step.block, found: name });
    }
  }
  const cleared = blueprint.clear.filter((cell) => {
    const { name } = nameAt(cell);
    return name !== undefined && EMPTY.has(name);
  }).length;
  return {
    total: blueprint.place.length,
    matched,
    unknown,
    cleared,
    clearTotal: blueprint.clear.length,
    missing,
  };
}

function int(value: JsonValue | undefined, what: string, limit: number): number {
  if (typeof value !== "number" || !Number.isInteger(value) || Math.abs(value) > limit) {
    throw new CheckInputError(`${what} must be an integer within ±${String(limit)}`);
  }
  return value;
}

function relative(value: JsonValue, what: string): RelativeCell {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new CheckInputError(`${what} must be { a, b, c }`);
  }
  return {
    a: int(value.a, `${what}.a`, 64),
    b: int(value.b, `${what}.b`, 64),
    c: int(value.c, `${what}.c`, 64),
  };
}

/** Parses a blueprint that comes back from the core (it was ours, but it crossed a process). */
export function parseBlueprint(value: JsonValue | undefined): Blueprint {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new CheckInputError("`blueprint` must be { clear, place }");
  }
  const { clear = [], place = [] } = value;
  if (!Array.isArray(clear) || !Array.isArray(place) || clear.length + place.length > MAX_CELLS) {
    throw new CheckInputError(`\`blueprint\` needs arrays with at most ${String(MAX_CELLS)} cells`);
  }
  return {
    clear: clear.map((cell, i) => relative(cell, `clear[${String(i)}]`)),
    place: place.map((step, i): PlaceStep => {
      const cell = relative(step, `place[${String(i)}]`);
      const block =
        typeof step === "object" && step !== null && !Array.isArray(step) ? step.block : null;
      if (typeof block !== "string" || !/^[a-z0-9_]{1,64}$/.test(block)) {
        throw new CheckInputError(`place[${String(i)}].block must be a block name`);
      }
      return { ...cell, block, item: block };
    }),
  };
}

export function parseOrigin(value: JsonValue | undefined): Cell {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new CheckInputError("`origin` must be { x, y, z }");
  }
  return {
    x: int(value.x, "origin.x", 30_000_000),
    y: int(value.y, "origin.y", 320),
    z: int(value.z, "origin.z", 30_000_000),
  };
}

export function parseFacing(value: JsonValue | undefined): Facing {
  if (!isFacing(value)) {
    throw new CheckInputError("`facing` must be north, east, south or west");
  }
  return value;
}
