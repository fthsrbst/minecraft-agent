/**
 * Record a skill v1 (plan P4.1, research.md §4.6): a recording of block changes becomes a
 * blueprint (the net change, relative to the demonstrator), and the blueprint becomes a skill whose
 * code is generated here, deterministically, with no LLM. Only the naming and the intent card come
 * from L2, in the core.
 *
 * What v1 cannot capture (kept as `unsupported` and reported, never silently dropped): block states
 * (stairs facing, slabs top/bottom), blocks with no item of the same name, and cells that cannot be
 * placed on top of something solid (overhangs; `bot.place` needs a solid block below).
 */
import type { JsonObject } from "../rpc/json-rpc.js";
import type { Facing, RelativeCell } from "./frame.js";

/** One observed block change, relative to the anchor. `from`/`to` are block names. */
export interface BlockEvent extends RelativeCell {
  readonly t: number; // ms since #record start
  readonly from: string;
  readonly to: string;
}

export interface Note {
  readonly t: number;
  readonly text: string;
}

export interface Recording {
  readonly player: string;
  readonly facing: Facing;
  readonly durationMs: number;
  readonly events: readonly BlockEvent[];
  readonly notes: readonly Note[];
  readonly truncated: boolean;
}

export interface PlaceStep extends RelativeCell {
  readonly block: string;
  readonly item: string;
}

export interface Blueprint {
  readonly clear: readonly RelativeCell[];
  readonly place: readonly PlaceStep[];
}

export interface Compiled {
  readonly blueprint: Blueprint;
  readonly materials: Readonly<Record<string, number>>;
  readonly unsupported: readonly string[];
  /** Changes that undid each other (placed then broken): detours, removed from the blueprint. */
  readonly detours: number;
  readonly summary: string;
}

// Blocks a player does not "build" with: changes to these are the world moving, not the demo.
const EMPTY: ReadonlySet<string> = new Set(["air", "cave_air", "void_air"]);
const NOISE: ReadonlySet<string> = new Set([
  "water",
  "lava",
  "fire",
  "soul_fire",
  "short_grass",
  "tall_grass",
  "snow",
]);

const key = (cell: RelativeCell): string => `${String(cell.a)},${String(cell.b)},${String(cell.c)}`;

/**
 * The net change per cell: the first `from` against the last `to`. A cell that ends as it began
 * (placed, then broken) is a detour and drops out.
 */
export function compile(recording: Recording, isItem: (name: string) => boolean): Compiled {
  const first = new Map<string, BlockEvent>();
  const last = new Map<string, BlockEvent>();
  for (const event of [...recording.events].sort((p, q) => p.t - q.t)) {
    const k = key(event);
    if (!first.has(k)) {
      first.set(k, event);
    }
    last.set(k, event);
  }
  const clear: RelativeCell[] = [];
  const place: PlaceStep[] = [];
  const unsupported: string[] = [];
  let detours = 0;
  for (const [k, end] of last) {
    const start = first.get(k) ?? end;
    const before = start.from;
    const after = end.to;
    if (before === after) {
      detours += 1;
      continue;
    }
    const cell = { a: end.a, b: end.b, c: end.c };
    if (NOISE.has(after) || (NOISE.has(before) && EMPTY.has(after))) {
      continue;
    }
    if (EMPTY.has(after)) {
      clear.push(cell);
    } else if (isItem(after)) {
      place.push({ ...cell, block: after, item: after });
    } else {
      unsupported.push(`${after} at ${k} (no item of that name)`);
    }
  }
  // Bottom up, so each block has its support; then a fixed order so the code is reproducible.
  const order = (p: RelativeCell, q: RelativeCell): number => p.b - q.b || p.c - q.c || p.a - q.a;
  clear.sort((p, q) => q.b - p.b || p.c - q.c || p.a - q.a); // top down: never dig out support
  place.sort(order);
  const placed = new Set(place.map(key));
  for (const step of place) {
    const below = key({ a: step.a, b: step.b - 1, c: step.c });
    if (step.b > minB(place) && !placed.has(below)) {
      unsupported.push(`${step.block} at ${key(step)} may hang in the air (nothing placed below)`);
    }
  }
  const materials: Record<string, number> = {};
  for (const step of place) {
    materials[step.item] = (materials[step.item] ?? 0) + 1;
  }
  const summary =
    `${String(place.length)} block(s) to place` +
    (clear.length > 0 ? `, ${String(clear.length)} to clear` : "") +
    (Object.keys(materials).length > 0
      ? ` (${Object.entries(materials)
          .map(([item, count]) => `${String(count)} ${item}`)
          .join(", ")})`
      : "") +
    ` in a ${size(place, clear)} area`;
  return { blueprint: { clear, place }, materials, unsupported, detours, summary };
}

function minB(cells: readonly RelativeCell[]): number {
  return cells.reduce((low, cell) => Math.min(low, cell.b), Number.POSITIVE_INFINITY);
}

function size(...groups: readonly (readonly RelativeCell[])[]): string {
  const cells = groups.flat();
  if (cells.length === 0) {
    return "0×0×0";
  }
  const span = (pick: (cell: RelativeCell) => number): number =>
    Math.max(...cells.map(pick)) - Math.min(...cells.map(pick)) + 1;
  return `${String(span((c) => c.a))}×${String(span((c) => c.c))}×${String(span((c) => c.b))}`;
}

/**
 * The skill body (it runs in the skill executor with `bot`, `args`, `log`). `args.origin` and
 * `args.facing` say where to build; by default where the bot stands, facing where it looks, like
 * the demonstrator did. The bot first steps out of the build area, so it never stands in a cell
 * it must fill. Cells that already hold the right block are skipped, so a re-run continues.
 */
export function skillCode(blueprint: Blueprint, summary: string): string {
  const plan = JSON.stringify({ clear: blueprint.clear, place: blueprint.place });
  const minC = Math.min(0, ...blueprint.place.map((s) => s.c), ...blueprint.clear.map((s) => s.c));
  return `// Demonstrated build (record a skill v1): ${summary.replace(/[\r\n]/g, " ")}
const PLAN = ${plan};
const FACINGS = ["north", "west", "south", "east"];
const FORWARD = { north: [0, -1], east: [1, 0], south: [0, 1], west: [-1, 0] };
const start = await bot.observe({ nearby: false });
const origin = args.origin ?? {
  x: Math.floor(start.position.x),
  y: Math.floor(start.position.y),
  z: Math.floor(start.position.z),
};
const facing =
  args.facing ?? FACINGS[(((Math.round(start.yaw / (Math.PI / 2)) % 4) + 4) % 4)];
const [fx, fz] = FORWARD[facing];
const [rx, rz] = [-fz, fx];
const at = (cell) => ({
  x: origin.x + cell.a * rx + cell.c * fx,
  y: origin.y + cell.b,
  z: origin.z + cell.a * rz + cell.c * fz,
});
// Stand two cells behind the build, outside every cell the plan fills.
const stand = at({ a: 0, b: 0, c: ${String(minC - 2)} });
try {
  await bot.goTo(stand.x, stand.y, stand.z, { range: 1 });
} catch (error) {
  log("could not reach the standing spot; building from here:", String(error));
}
let placed = 0;
let skipped = 0;
for (const cell of PLAN.clear) {
  const p = at(cell);
  try {
    await bot.dig(p.x, p.y, p.z);
  } catch (error) {
    log("clear skipped at", p, String(error));
  }
}
for (const step of PLAN.place) {
  const p = at(step);
  try {
    await bot.place(step.item, p);
    placed += 1;
  } catch (error) {
    // An occupied cell is left as it is (a re-run, or the block was already there); the
    // independent structure check decides whether it is the right block.
    if (!String(error).includes("must be free")) {
      throw error;
    }
    skipped += 1;
  }
}
return { ok: true, placed, skipped, origin, facing };
`;
}

export function compiledJson(compiled: Compiled, code: string): JsonObject {
  return {
    blueprint: {
      clear: compiled.blueprint.clear.map((c) => ({ ...c })),
      place: compiled.blueprint.place.map((s) => ({ ...s })),
    },
    materials: { ...compiled.materials },
    unsupported: [...compiled.unsupported],
    detours: compiled.detours,
    summary: compiled.summary,
    code,
  };
}
