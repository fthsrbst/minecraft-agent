import { describe, expect, it } from "vitest";

import {
  floodOpenSpace,
  parseObserveOptions,
  parseVisibility,
  summarizeBlocks,
} from "./observation.js";

describe("summarizeBlocks", () => {
  it("groups by name with count and nearest position, nearest type first", () => {
    const origin = { x: 0, y: 64, z: 0 };
    const summary = summarizeBlocks(
      [
        { name: "stone", position: { x: 0, y: 60, z: 0 } },
        { name: "oak_log", position: { x: 5, y: 64, z: 0 } },
        { name: "stone", position: { x: 0, y: 62, z: 0 } },
        { name: "oak_log", position: { x: 9, y: 64, z: 0 } },
        { name: "oak_log", position: { x: 6, y: 64, z: 0 } },
      ],
      origin,
    );
    expect(summary).toEqual([
      { name: "stone", count: 2, nearest: { x: 0, y: 62, z: 0 }, distance: 2 },
      { name: "oak_log", count: 3, nearest: { x: 5, y: 64, z: 0 }, distance: 5 },
    ]);
  });

  it("returns nothing for no sightings", () => {
    expect(summarizeBlocks([], { x: 0, y: 0, z: 0 })).toEqual([]);
  });
});

describe("floodOpenSpace", () => {
  // Solid everywhere except the listed open cells.
  const world = (openCells: string[]) => {
    const open = new Set(openCells);
    return (x: number, y: number, z: number) => open.has(`${String(x)},${String(y)},${String(z)}`);
  };

  it("reaches connected open cells only; a sealed pocket stays hidden", () => {
    // A corridor along x from the start, and a sealed pocket at (0, 3, 0).
    const space = floodOpenSpace(
      { x: 0, y: 0, z: 0 },
      5,
      world(["0,0,0", "1,0,0", "2,0,0", "0,3,0"]),
    );
    expect([...space.open].sort()).toEqual(["0,0,0", "1,0,0", "2,0,0"]);
    expect(space.truncated).toBe(false);
  });

  it("returns the solid boundary of the open space: what can be seen", () => {
    const space = floodOpenSpace({ x: 0, y: 0, z: 0 }, 5, world(["0,0,0", "1,0,0"]));
    const keys = new Set(space.boundary.map((p) => `${String(p.x)},${String(p.y)},${String(p.z)}`));
    expect(keys.has("2,0,0")).toBe(true); // end of the corridor
    expect(keys.has("0,1,0")).toBe(true); // ceiling
    expect(keys.has("3,0,0")).toBe(false); // behind the first solid block
    expect(keys.has("0,3,0")).toBe(false); // the sealed pocket's walls
    expect(space.boundary).toHaveLength(10);
    expect(space.boundaryKeys.size).toBe(10);
  });

  it("stops at the radius and reports a cut budget", () => {
    const everything = () => true;
    expect(floodOpenSpace({ x: 0, y: 0, z: 0 }, 1, everything).open.size).toBe(7);
    const cut = floodOpenSpace({ x: 0, y: 0, z: 0 }, 10, everything, 50);
    expect(cut.open.size).toBeLessThanOrEqual(56);
    expect(cut.truncated).toBe(true);
  });

  it("is empty when the start is not open", () => {
    expect(floodOpenSpace({ x: 0, y: 0, z: 0 }, 5, () => false).open.size).toBe(0);
  });
});

describe("parseVisibility", () => {
  it("defaults to fair", () => {
    expect(parseVisibility(undefined)).toBe("fair");
    expect(parseVisibility("full")).toBe("full");
  });

  it("rejects other values", () => {
    expect(() => parseVisibility("xray")).toThrow(/MC_VISIBILITY/);
  });
});

describe("parseObserveOptions", () => {
  it("defaults to nearby within 16 blocks", () => {
    expect(parseObserveOptions({}, "fair")).toEqual({
      nearby: true,
      radius: 16,
      visibility: "fair",
    });
  });

  it.each([{ nearby: "yes" }, { radius: 0 }, { radius: 33 }, { radius: 2.5 }])(
    "rejects %o",
    (params) => {
      expect(() => parseObserveOptions(params, "full")).toThrow(RangeError);
    },
  );
});
