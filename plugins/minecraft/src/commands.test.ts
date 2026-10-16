import { describe, expect, it } from "vitest";

import { loadCommands } from "./commands.js";

describe("loadCommands", () => {
  it("loads the shipped vocabulary with inlined skill code", () => {
    const vocabulary = loadCommands(new URL("../commands/", import.meta.url));
    const commands = vocabulary.commands as { name: string; code?: string; builtin?: string }[];
    expect(vocabulary.prefix).toBe("#");
    expect(commands.map((c) => c.name)).toEqual([
      "goto",
      "mine",
      "follow",
      "stop",
      "sethome",
      "places",
      "help",
    ]);
    expect(commands.find((c) => c.name === "goto")?.code).toContain("bot.goTo");
    expect(commands.find((c) => c.name === "stop")?.builtin).toBe("stop");
  });
});
