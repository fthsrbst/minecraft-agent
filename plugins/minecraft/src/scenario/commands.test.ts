import { describe, expect, it } from "vitest";

import type { JsonObject } from "../rpc/json-rpc.js";
import { isFailureReply, parsePlayer, resetCommands, setupCommands } from "./commands.js";

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
    ["unknown field", { summon: "zombie" }, /unknown setup field\(s\): summon/],
  ])("rejects %s", (_name, spec, message) => {
    expect(() => setupCommands("AgentBot", spec)).toThrow(message);
  });
});

describe("resetCommands", () => {
  it("clears the inventory and the drops around the player", () => {
    const commands = resetCommands("AgentBot");
    expect(commands[0]).toBe("clear AgentBot");
    expect(commands).toContain(
      "execute at AgentBot run kill @e[type=minecraft:item,distance=..64]",
    );
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
  });
});
