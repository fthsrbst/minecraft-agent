import { describe, expect, it } from "vitest";

import { chooseReflex, type ReflexState } from "./rules.js";

const calm: ReflexState = {
  health: 20,
  food: 20,
  oxygen: 20,
  threats: [],
  hasWeapon: true,
  hasFood: true,
  working: false,
};
const zombie = (distance: number, id = 1) => ({ id, name: "zombie", distance });

describe("chooseReflex", () => {
  it("swims up before anything else when the air runs low", () => {
    const choice = chooseReflex({ ...calm, oxygen: 6, threats: [zombie(2)] });
    expect(choice).toMatchObject({ kind: "surface" });
    expect(chooseReflex({ ...calm, oxygen: 12 })).toBeNull();
  });

  it("does nothing when all is well", () => {
    expect(chooseReflex(calm)).toBeNull();
  });

  it("fights a single zombie when healthy and armed", () => {
    expect(chooseReflex({ ...calm, threats: [zombie(4)] })).toMatchObject({ kind: "fight" });
  });

  it("ignores hostiles out of range and neutral mobs", () => {
    const threats = [zombie(12), { id: 2, name: "enderman", distance: 2 }];
    expect(chooseReflex({ ...calm, threats })).toBeNull();
  });

  it("flees from a creeper even at full health, and earlier", () => {
    const choice = chooseReflex({ ...calm, threats: [{ id: 3, name: "creeper", distance: 9 }] });
    expect(choice).toMatchObject({ kind: "flee", reason: "creeper is too dangerous to fight" });
  });

  it("flees when health is low", () => {
    expect(chooseReflex({ ...calm, health: 6, threats: [zombie(3)] })).toMatchObject({
      kind: "flee",
    });
  });

  it("flees from a pack", () => {
    const threats = [zombie(3, 1), zombie(4, 2), zombie(5, 3)];
    expect(chooseReflex({ ...calm, threats })).toMatchObject({ kind: "flee" });
  });

  it("never fights unarmed", () => {
    expect(chooseReflex({ ...calm, hasWeapon: false, threats: [zombie(3)] })).toMatchObject({
      kind: "flee",
      reason: "no weapon",
    });
  });

  it("targets the nearest threat", () => {
    const choice = chooseReflex({ ...calm, threats: [zombie(7, 1), zombie(2, 2)] });
    expect(choice).toMatchObject({ kind: "fight", target: { id: 2 } });
  });

  it("eats when hungry and idle, or starving while working", () => {
    expect(chooseReflex({ ...calm, food: 12 })).toMatchObject({ kind: "eat" });
    expect(chooseReflex({ ...calm, food: 12, working: true })).toBeNull();
    expect(chooseReflex({ ...calm, food: 5, working: true })).toMatchObject({ kind: "eat" });
    expect(chooseReflex({ ...calm, food: 5, hasFood: false })).toBeNull();
  });

  it("puts danger before hunger", () => {
    expect(chooseReflex({ ...calm, food: 2, threats: [zombie(3)] })).toMatchObject({
      kind: "fight",
    });
  });
});
