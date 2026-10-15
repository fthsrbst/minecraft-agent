import { describe, expect, it } from "vitest";

import { BotConfigError, loadBotConfig } from "./bot-config.js";

describe("loadBotConfig", () => {
  it("uses local defaults when nothing is set", () => {
    expect(loadBotConfig({})).toEqual({ host: "127.0.0.1", port: 25565, username: "AgentBot" });
  });

  it("reads values from the environment", () => {
    const config = loadBotConfig({
      MC_HOST: "localhost",
      MC_PORT: "25570",
      MC_USERNAME: "Steve_2",
    });
    expect(config).toEqual({ host: "localhost", port: 25570, username: "Steve_2" });
  });

  it.each(["example.com", "192.168.1.10", "0.0.0.0"])("refuses non-local host %s", (host) => {
    expect(() => loadBotConfig({ MC_HOST: host })).toThrow(BotConfigError);
  });

  it.each(["0", "65536", "abc", "25565.5"])("refuses invalid port %s", (port) => {
    expect(() => loadBotConfig({ MC_PORT: port })).toThrow(/not a valid TCP port/);
  });

  it.each(["ab", "a".repeat(17), "bad name", "bad-name"])(
    "refuses invalid username %s",
    (username) => {
      expect(() => loadBotConfig({ MC_USERNAME: username })).toThrow(/valid Minecraft username/);
    },
  );
});
