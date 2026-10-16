import { Vec3 } from "vec3";
import { describe, expect, it } from "vitest";

import { checkStructure, parseBlueprint, parseFacing, parseOrigin } from "./check.js";

const world = new Map<string, string>([
  ["101,70,100", "oak_planks"],
  ["102,70,100", "dirt"],
]);
const bot = {
  blockAt: (p: Vec3) => {
    const name = world.get(`${String(p.x)},${String(p.y)},${String(p.z)}`);
    return p.x > 200 ? null : ({ name: name ?? "air" } as never);
  },
};

describe("checkStructure", () => {
  const blueprint = parseBlueprint({
    place: [
      { a: 0, b: 0, c: 1, block: "oak_planks" },
      { a: 0, b: 0, c: 2, block: "oak_planks" },
    ],
    clear: [{ a: 0, b: 0, c: 3 }],
  });

  it("counts placed blocks only and reports what is wrong", () => {
    const result = checkStructure(bot, blueprint, { x: 100, y: 70, z: 100 }, "east");
    expect(result).toMatchObject({ total: 2, matched: 1, unknown: 0, cleared: 1, clearTotal: 1 });
    expect(result.missing).toEqual([{ x: 102, y: 70, z: 100, want: "oak_planks", found: "dirt" }]);
  });

  it("counts unloaded cells as unknown, never as a match", () => {
    const result = checkStructure(bot, blueprint, { x: 300, y: 70, z: 100 }, "east");
    expect(result).toMatchObject({ total: 2, matched: 0, unknown: 2 });
  });
});

describe("parsing input from the core", () => {
  it("refuses malformed blueprints, origins and facings", () => {
    expect(() => parseBlueprint({ place: [{ a: 0, b: 0, c: 1, block: "x y" }] })).toThrow(/name/);
    expect(() => parseBlueprint({ place: [{ a: 0.5, b: 0, c: 1, block: "x" }] })).toThrow(
      /integer/,
    );
    expect(() => parseBlueprint({ place: "all" })).toThrow(/arrays/);
    expect(() => parseOrigin({ x: 1, y: 999, z: 1 })).toThrow(/origin.y/);
    expect(() => parseFacing("up")).toThrow(/facing/);
    expect(parseFacing("west")).toBe("west");
  });
});
