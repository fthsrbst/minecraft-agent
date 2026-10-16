/**
 * A recording is stored in the demonstrator's own frame (right, up, forward from where they stood
 * and faced at `#record start`), so a replay can rebuild it at another spot facing another way.
 * Only the four cardinal directions are used: blocks sit on a grid, and a build turned by 37° does
 * not exist.
 */

export type Facing = "north" | "east" | "south" | "west";

export const FACINGS: readonly Facing[] = ["north", "east", "south", "west"];

export interface Cell {
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

/** A position relative to an anchor: a = right, b = up, c = forward. */
export interface RelativeCell {
  readonly a: number;
  readonly b: number;
  readonly c: number;
}

const FORWARD: Readonly<Record<Facing, { x: number; z: number }>> = {
  north: { x: 0, z: -1 },
  east: { x: 1, z: 0 },
  south: { x: 0, z: 1 },
  west: { x: -1, z: 0 },
};

/**
 * Mineflayer's yaw: 0 looks north (-z) and grows counter-clockwise seen from above, so π/2 looks
 * west. The nearest cardinal direction wins.
 */
export function facingFromYaw(yaw: number): Facing {
  const turns = Math.round(yaw / (Math.PI / 2));
  const index = ((turns % 4) + 4) % 4;
  // Counter-clockwise from north: north, west, south, east.
  return (["north", "west", "south", "east"] as const)[index] ?? "north";
}

export function isFacing(value: unknown): value is Facing {
  return typeof value === "string" && (FACINGS as readonly string[]).includes(value);
}

function axes(facing: Facing): { f: { x: number; z: number }; r: { x: number; z: number } } {
  const f = FORWARD[facing];
  // Right of forward, seen from above with y up: (x, z) → (-z, x).
  return { f, r: { x: -f.z, z: f.x } };
}

export function toRelative(cell: Cell, anchor: Cell, facing: Facing): RelativeCell {
  const { f, r } = axes(facing);
  const dx = cell.x - anchor.x;
  const dz = cell.z - anchor.z;
  return { a: dx * r.x + dz * r.z, b: cell.y - anchor.y, c: dx * f.x + dz * f.z };
}

export function toWorld(cell: RelativeCell, origin: Cell, facing: Facing): Cell {
  const { f, r } = axes(facing);
  return {
    x: origin.x + cell.a * r.x + cell.c * f.x,
    y: origin.y + cell.b,
    z: origin.z + cell.a * r.z + cell.c * f.z,
  };
}
