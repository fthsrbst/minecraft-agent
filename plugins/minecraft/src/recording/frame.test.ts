import { describe, expect, it } from "vitest";

import { FACINGS, facingFromYaw, toRelative, toWorld } from "./frame.js";

describe("frame", () => {
  it("maps Mineflayer yaw to the nearest cardinal direction", () => {
    expect(facingFromYaw(0)).toBe("north");
    expect(facingFromYaw(Math.PI / 2)).toBe("west");
    expect(facingFromYaw(Math.PI)).toBe("south");
    expect(facingFromYaw(-Math.PI / 2)).toBe("east");
    expect(facingFromYaw(0.6)).toBe("north");
    expect(facingFromYaw(2 * Math.PI + 0.1)).toBe("north");
  });

  it("puts forward and right where a player facing north expects them", () => {
    const anchor = { x: 10, y: 64, z: 10 };
    expect(toRelative({ x: 10, y: 64, z: 9 }, anchor, "north")).toEqual({ a: 0, b: 0, c: 1 });
    expect(toRelative({ x: 11, y: 65, z: 10 }, anchor, "north")).toEqual({ a: 1, b: 1, c: 0 });
  });

  it("round-trips every cell in every facing", () => {
    const anchor = { x: -3, y: 70, z: 5 };
    for (const facing of FACINGS) {
      for (const cell of [
        { x: -1, y: 71, z: 4 },
        { x: -6, y: 70, z: 9 },
      ]) {
        expect(toWorld(toRelative(cell, anchor, facing), anchor, facing)).toEqual(cell);
      }
    }
  });

  it("turns a build with the builder", () => {
    // One block ahead and one to the right, facing east: +x is forward, +z is right.
    expect(toWorld({ a: 1, b: 0, c: 1 }, { x: 0, y: 0, z: 0 }, "east")).toEqual({
      x: 1,
      y: 0,
      z: 1,
    });
    expect(toWorld({ a: 1, b: 0, c: 1 }, { x: 0, y: 0, z: 0 }, "south")).toEqual({
      x: -1,
      y: 0,
      z: 1,
    });
  });
});
