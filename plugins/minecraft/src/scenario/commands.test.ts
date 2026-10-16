import { describe, expect, it } from "vitest";

import type { JsonObject } from "../rpc/json-rpc.js";
import {
  arenaCommands,
  isFailureReply,
  parsePlayer,
  resetCommands,
  setupCommands,
} from "./commands.js";

describe("setupCommands", () => {
  it("builds commands in a fixed order", () => {
    const spec: JsonObject = {
      weather: "clear",
      give: [{ item: "oak_log", count: 3 }, { item: "apple" }],
      teleport: { x: 10.5, y: 70, z: -4 },
      time: "night",
      clear: true,
    };
    expect(setupCommands("AgentBot", spec)).toEqual([
      "clear AgentBot",
      "tp AgentBot 10.5 70 -4",
      "give AgentBot minecraft:oak_log 3",
      "give AgentBot minecraft:apple 1",
      "time set 13000",
      "weather clear",
    ]);
  });

  it("accepts an empty spec", () => {
    expect(setupCommands("AgentBot", {})).toEqual([]);
  });

  it.each<[string, JsonObject, RegExp]>([
    ["unknown item", { give: [{ item: "unobtainium" }] }, /unknown item "unobtainium"/],
    ["injection in item", { give: [{ item: "stone 1\nop Fatih" }] }, /unknown item/],
    ["zero count", { give: [{ item: "stone", count: 0 }] }, /count/],
    ["huge count", { give: [{ item: "stone", count: 10_000 }] }, /count/],
    ["give not a list", { give: { item: "stone" } }, /list/],
    ["bad coordinate", { teleport: { x: "1", y: 70, z: 0 } }, /teleport\.x/],
    ["too high", { teleport: { x: 0, y: 1000, z: 0 } }, /teleport\.y/],
    ["bad time", { time: "dusk" }, /time/],
    ["bad weather", { weather: "snow" }, /weather/],
    ["bad clear", { clear: "yes" }, /clear/],
    ["unknown field", { op: "Fatih" }, /unknown setup field\(s\): op/],
    ["inherited item name", { give: [{ item: "constructor" }] }, /unknown item "constructor"/],
    ["air", { give: [{ item: "air" }] }, /unknown item "air"/],
    ["inherited time name", { time: "constructor" }, /time/],
  ])("rejects %s", (_name, spec, message) => {
    expect(() => setupCommands("AgentBot", spec)).toThrow(message);
  });
});

describe("terrain and entities", () => {
  it("orders terrain before the player and entities after", () => {
    expect(
      setupCommands("AgentBot", {
        summon: [{ entity: "zombie", x: 3, y: 65, z: 0 }],
        give: [{ item: "stone" }],
        teleport: { x: 0, y: 65, z: 0 },
        place: [{ block: "oak_log", x: 2, y: 65, z: 2 }],
        fill: [{ block: "stone", from: { x: -2, y: 64, z: -2 }, to: { x: 2, y: 64, z: 2 } }],
      }),
    ).toEqual([
      "fill -2 64 -2 2 64 2 minecraft:stone",
      "setblock 2 65 2 minecraft:oak_log",
      "tp AgentBot 0 65 0",
      "give AgentBot minecraft:stone 1",
      'summon minecraft:zombie 3 65 0 {Tags:["scenario"]}',
    ]);
  });

  it.each<[string, JsonObject, RegExp]>([
    ["unknown block", { place: [{ block: "unobtanium", x: 0, y: 64, z: 0 }] }, /unknown block/],
    [
      "fractional block coordinate",
      { place: [{ block: "stone", x: 0.5, y: 64, z: 0 }] },
      /place\.x/,
    ],
    ["below the world", { place: [{ block: "stone", x: 0, y: -65, z: 0 }] }, /place\.y/],
    [
      "huge fill",
      { fill: [{ block: "stone", from: { x: 0, y: 0, z: 0 }, to: { x: 99, y: 9, z: 99 } }] },
      /fill volume 100000/,
    ],
    ["summon a player", { summon: [{ entity: "player", x: 0, y: 64, z: 0 }] }, /unknown entity/],
    ["unknown entity", { summon: [{ entity: "dragonling", x: 0, y: 64, z: 0 }] }, /unknown entity/],
    [
      "offset too far",
      { summon: [{ entity: "zombie", offset: { x: 99, y: 0, z: 0 } }] },
      /summon\.offset\.x/,
    ],
    [
      "too many summons",
      { summon: Array(21).fill({ entity: "pig", x: 0, y: 64, z: 0 }) },
      /at most 20/,
    ],
  ])("rejects %s", (_name, spec, message) => {
    expect(() => setupCommands("AgentBot", spec)).toThrow(message);
  });
});

describe("summon relative to the player", () => {
  it("uses execute at the player with relative coordinates", () => {
    expect(
      setupCommands("AgentBot", { summon: [{ entity: "zombie", offset: { x: 4, y: 0, z: -1 } }] }),
    ).toEqual(['execute at AgentBot run summon minecraft:zombie ~4 ~0 ~-1 {Tags:["scenario"]}']);
  });
});

describe("teleport formatting", () => {
  it("never uses exponent notation", () => {
    expect(setupCommands("AgentBot", { teleport: { x: 1e-7, y: 64, z: -2.5 } })).toEqual([
      "tp AgentBot 0 64 -2.5",
    ]);
    expect(setupCommands("AgentBot", { teleport: { x: 1e7, y: 70.125, z: 0.5 } })).toEqual([
      "tp AgentBot 10000000 70.125 0.5",
    ]);
  });
});

describe("resetCommands", () => {
  it("clears the inventory, scenario mobs and the drops around the player", () => {
    const commands = resetCommands("AgentBot");
    expect(commands[0]).toBe("kill @e[tag=scenario]");
    expect(commands).toContain("clear AgentBot");
    expect(commands).toContain(
      "execute at AgentBot run kill @e[type=minecraft:item,distance=..64]",
    );
  });

  it("teleports to the spawn point first when one is given", () => {
    expect(resetCommands("AgentBot", { x: 1, y: 70, z: 2 })[0]).toBe("tp AgentBot 1 70 2");
  });
});

describe("parsePlayer", () => {
  it.each(["AgentBot", "a_b"])("accepts %s", (name) => {
    expect(parsePlayer(name)).toBe(name);
  });

  it.each(["@a", "x", "Agent Bot", 3])("rejects %s", (name) => {
    expect(() => parsePlayer(name)).toThrow(/player/);
  });
});

describe("isFailureReply", () => {
  it("detects error replies", () => {
    expect(isFailureReply("No player was found")).toBe(true);
    expect(isFailureReply("Unknown or incomplete command, see below for error")).toBe(true);
    expect(isFailureReply("Gave 3 [Oak Log] to AgentBot")).toBe(false);
    expect(isFailureReply("No entity was found", "summon minecraft:pig 0 64 0")).toBe(true);
  });

  it("accepts an empty kill", () => {
    expect(isFailureReply("No entity was found", "kill @e[tag=scenario]")).toBe(false);
    expect(isFailureReply("No entity was found", "execute at A run kill @e[type=item]")).toBe(
      false,
    );
  });
});

describe("arenaCommands", () => {
  it("builds a separate flat spot per index, facing the given way", () => {
    const first = arenaCommands("AgentBot", 0, "east", [{ item: "oak_planks", count: 9 }]);
    const second = arenaCommands("AgentBot", 1, "north", []);
    expect(first.origin).toEqual({ x: 2000, y: 100, z: 2000 });
    expect(second.origin.x).toBe(2048);
    expect(arenaCommands("AgentBot", 2, undefined, []).facing).toBe("south");
    expect(first.commands).toContain("tp AgentBot 2000.5 100 2000.5 -90 0");
    expect(first.commands.at(-1)).toBe("give AgentBot minecraft:oak_planks 9");
    expect(first.commands[1]).toBe("fill 1992 99 1992 2008 99 2008 minecraft:stone");
  });

  it("refuses bad input", () => {
    expect(() => arenaCommands("AgentBot", -1, "east", [])).toThrow(/index/);
    expect(() => arenaCommands("AgentBot", 0, "up", [])).toThrow(/facing/);
    expect(() => arenaCommands("AgentBot", 0, "east", [{ item: "nope" }])).toThrow(/unknown item/);
  });
});
