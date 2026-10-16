import { describe, expect, it } from "vitest";

import { isExposed, parseObserveOptions, parseVisibility, summarizeBlocks } from "./observation.js";

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

describe("isExposed", () => {
  it("is exposed when any neighbour is open or unloaded", () => {
    expect(isExposed(["stone", "stone", "air", "stone", "stone", "stone"])).toBe(true);
    expect(isExposed(["stone", "water", "stone", "stone", "stone", "stone"])).toBe(true);
    expect(isExposed(["stone", null, "stone", "stone", "stone", "stone"])).toBe(true);
  });

  it("is hidden when every neighbour is solid", () => {
    expect(isExposed(["stone", "dirt", "stone", "granite", "stone", "iron_ore"])).toBe(false);
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
