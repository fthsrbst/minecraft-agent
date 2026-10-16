import { describe, expect, it } from "vitest";

import {
  floodOpenSpace,
  parseObserveOptions,
  parseVisibility,
  summarizeBlocks,
  touchesOpenSpace,
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
  // A 7×7×7 world: solid everywhere except the cells listed as open.
  const world = (openCells: string[]) => {
    const open = new Set(openCells);
    return (x: number, y: number, z: number) => open.has(`${String(x)},${String(y)},${String(z)}`);
  };

  it("reaches connected open cells only", () => {
    // A corridor along x from the start, and a sealed pocket at (0, 3, 0).
    const isOpen = world(["0,0,0", "1,0,0", "2,0,0", "0,3,0"]);
    const open = floodOpenSpace({ x: 0, y: 0, z: 0 }, 5, isOpen);
    expect([...open].sort()).toEqual(["0,0,0", "1,0,0", "2,0,0"]);
  });

  it("stops at the radius and the cell budget", () => {
    const everything = () => true;
    expect(floodOpenSpace({ x: 0, y: 0, z: 0 }, 1, everything).size).toBe(7);
    expect(floodOpenSpace({ x: 0, y: 0, z: 0 }, 10, everything, 50).size).toBeLessThanOrEqual(56);
  });

  it("is empty when the start is not open", () => {
    expect(floodOpenSpace({ x: 0, y: 0, z: 0 }, 5, () => false).size).toBe(0);
  });
});

describe("touchesOpenSpace", () => {
  const open = new Set(["0,0,0", "1,0,0"]);

  it("sees a block next to the open space", () => {
    expect(touchesOpenSpace({ x: 2, y: 0, z: 0 }, open)).toBe(true);
    expect(touchesOpenSpace({ x: 0, y: -1, z: 0 }, open)).toBe(true);
  });

  it("does not see a block two cells away (e.g. ore behind stone)", () => {
    expect(touchesOpenSpace({ x: 3, y: 0, z: 0 }, open)).toBe(false);
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
