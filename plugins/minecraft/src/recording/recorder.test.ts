import { EventEmitter } from "node:events";

import type { Block } from "prismarine-block";
import { Vec3 } from "vec3";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MAX_RECORDING_MS, Recorder } from "./recorder.js";

class FakeWorld extends EventEmitter {
  players: Record<string, { entity?: { position: Vec3; yaw: number } }> = {
    Teacher: { entity: { position: new Vec3(10.5, 64, 10.5), yaw: 0 } },
  };
}

const block = (name: string, x: number, y: number, z: number): Block =>
  ({ name, position: new Vec3(x, y, z) }) as unknown as Block;

function setup(busy = false): { world: FakeWorld; recorder: Recorder; ended: string[] } {
  const world = new FakeWorld();
  const ended: string[] = [];
  const recorder = new Recorder(() => world, {
    botBusy: () => busy,
    ended: (player, reason) => ended.push(`${player}: ${reason}`),
  });
  return { world, recorder, ended };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("Recorder", () => {
  it("records nearby changes relative to the player and their notes", () => {
    const { world, recorder } = setup();
    expect(recorder.start("Teacher")).toEqual({ anchor: { x: 10, y: 64, z: 10 }, facing: "north" });
    world.emit("blockUpdate", block("air", 10, 64, 9), block("oak_planks", 10, 64, 9));
    world.emit("chat", "Teacher", "// first row");
    world.emit("chat", "Teacher", "hello"); // not a note
    world.emit("chat", "Other", "// not the teacher");
    const recording = recorder.stop();
    expect(recording.events).toMatchObject([{ a: 0, b: 0, c: 1, from: "air", to: "oak_planks" }]);
    expect(recording.notes.map((n) => n.text)).toEqual(["first row"]);
    expect(world.listenerCount("blockUpdate")).toBe(0);
    expect(world.listenerCount("chat")).toBe(0);
  });

  it("ignores changes out of reach, of unknown blocks, or made while the bot works", () => {
    const busy = setup(true);
    busy.recorder.start("Teacher");
    busy.world.emit("blockUpdate", block("air", 10, 64, 9), block("stone", 10, 64, 9));
    expect(busy.recorder.stop().events).toEqual([]);

    const { world, recorder } = setup();
    recorder.start("Teacher");
    world.emit("blockUpdate", block("air", 30, 64, 9), block("stone", 30, 64, 9)); // far away
    world.emit("blockUpdate", null, block("stone", 10, 64, 9)); // unloaded before
    world.emit("blockUpdate", block("stone", 10, 64, 9), block("stone", 10, 64, 9)); // no change
    expect(recorder.stop().events).toEqual([]);
  });

  it("refuses a player it cannot see and a second recording", () => {
    const { recorder } = setup();
    expect(() => recorder.start("Nobody")).toThrow(/cannot see Nobody/);
    recorder.start("Teacher");
    expect(() => recorder.start("Teacher")).toThrow(/already recording/);
    recorder.stop();
    expect(() => recorder.stop()).toThrow(/not recording/);
  });

  it("ends on its own at the time limit, tells the core, and keeps what it saw", () => {
    vi.useFakeTimers();
    const { world, recorder, ended } = setup();
    recorder.start("Teacher");
    world.emit("blockUpdate", block("air", 10, 64, 9), block("stone", 10, 64, 9));
    vi.advanceTimersByTime(MAX_RECORDING_MS + 1);
    expect(ended).toEqual(["Teacher: the 10 minute limit was reached"]);
    expect(recorder.recording).toBeNull();
    const recording = recorder.stop();
    expect(recording.truncated).toBe(true);
    expect(recording.events).toHaveLength(1);
  });
});
