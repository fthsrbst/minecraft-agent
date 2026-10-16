import { describe, expect, it } from "vitest";

import { checkSkillSource, syntaxProblem } from "../skills/static-check.js";
import { type BlockEvent, compile, type Recording, skillCode } from "./blueprint.js";

const isItem = (name: string): boolean => !name.startsWith("wall_") && name !== "piston_head";
let clock = 0;
const event = (a: number, b: number, c: number, from: string, to: string): BlockEvent => ({
  a,
  b,
  c,
  from,
  to,
  t: (clock += 100),
});
const recording = (events: BlockEvent[]): Recording => ({
  player: "Teacher",
  facing: "north",
  durationMs: 9_000,
  events,
  notes: [{ t: 50, text: "a 3x3 floor" }],
  truncated: false,
});

function platform(): BlockEvent[] {
  const events: BlockEvent[] = [];
  for (let c = 1; c <= 3; c++) {
    for (let a = -1; a <= 1; a++) {
      events.push(event(a, 0, c, "air", "oak_planks"));
    }
  }
  return events;
}

describe("compile", () => {
  it("turns a demonstrated 3x3 floor into nine placements and their materials", () => {
    const compiled = compile(recording(platform()), isItem);
    expect(compiled.blueprint.place).toHaveLength(9);
    expect(compiled.materials).toEqual({ oak_planks: 9 });
    expect(compiled.unsupported).toEqual([]);
    expect(compiled.summary).toBe("9 block(s) to place (9 oak_planks) in a 3×3×1 area");
  });

  it("drops detours and keeps only the net change", () => {
    const events = [
      ...platform(),
      event(5, 0, 5, "air", "dirt"),
      event(5, 0, 5, "dirt", "air"), // placed by mistake, then removed
      event(0, 0, 1, "oak_planks", "stone"), // replaced: the last block wins
    ];
    const compiled = compile(recording(events), isItem);
    expect(compiled.detours).toBe(1);
    expect(compiled.blueprint.place.find((s) => s.a === 0 && s.c === 1)?.block).toBe("stone");
    expect(compiled.blueprint.place).toHaveLength(9);
  });

  it("records removals as cells to clear and ignores fluids and plants", () => {
    const events = [
      event(0, -1, 2, "grass_block", "air"),
      event(1, 0, 1, "air", "water"),
      event(2, 0, 1, "short_grass", "air"),
    ];
    const compiled = compile(recording(events), isItem);
    expect(compiled.blueprint.clear).toEqual([{ a: 0, b: -1, c: 2 }]);
    expect(compiled.blueprint.place).toEqual([]);
  });

  it("reports what v1 cannot rebuild instead of dropping it silently", () => {
    const events = [event(0, 0, 1, "air", "wall_torch"), event(0, 3, 1, "air", "stone")];
    const compiled = compile(recording([...events, event(0, 0, 2, "air", "stone")]), isItem);
    expect(compiled.unsupported.some((u) => u.startsWith("wall_torch"))).toBe(true);
    expect(compiled.unsupported.some((u) => u.includes("may hang in the air"))).toBe(true);
  });

  it("orders placements bottom up", () => {
    const events = [event(0, 1, 1, "air", "stone"), event(0, 0, 1, "air", "stone")];
    const compiled = compile(recording(events), isItem);
    expect(compiled.blueprint.place.map((s) => s.b)).toEqual([0, 1]);
  });
});

describe("skillCode", () => {
  const compiled = compile(recording(platform()), isItem);
  const code = skillCode(compiled.blueprint, compiled.summary);

  it("passes the executor's static rules and compiles", () => {
    expect(checkSkillSource(code)).toEqual([]);
    expect(syntaxProblem(code)).toBeNull();
  });

  it("builds the plan at the given origin, turned to the given facing", async () => {
    const placed: { item: string; x: number; y: number; z: number }[] = [];
    let stood: number[] = [];
    const bot = {
      observe: () => Promise.resolve({ position: { x: 0.5, y: 64, z: 0.5 }, yaw: 0 }),
      goTo: (x: number, y: number, z: number) => {
        stood = [x, y, z];
        return Promise.resolve({ ok: true });
      },
      dig: () => Promise.resolve({ ok: true }),
      place: (item: string, p: { x: number; y: number; z: number }) => {
        placed.push({ item, ...p });
        return Promise.resolve({ ok: true });
      },
    };
    type Body = (...values: unknown[]) => Promise<unknown>;
    const AsyncFunction = (async (): Promise<void> => {
      await Promise.resolve();
    }).constructor as new (...args: string[]) => Body;
    const run = new AsyncFunction("bot", "args", "log", code);
    const result = await run(
      bot,
      { origin: { x: 100, y: 70, z: 100 }, facing: "east" },
      () => undefined,
    );
    expect(result).toMatchObject({ ok: true, placed: 9, skipped: 0, facing: "east" });
    // Facing east, forward is +x: the floor spans x 101..103, z 99..101 (right is +z).
    expect(Math.min(...placed.map((p) => p.x))).toBe(101);
    expect(Math.max(...placed.map((p) => p.x))).toBe(103);
    expect(new Set(placed.map((p) => p.z))).toEqual(new Set([99, 100, 101]));
    expect(placed.every((p) => p.y === 70 && p.item === "oak_planks")).toBe(true);
    // It stands behind the build, outside it.
    expect(stood).toEqual([98, 70, 100]);
  });
});
