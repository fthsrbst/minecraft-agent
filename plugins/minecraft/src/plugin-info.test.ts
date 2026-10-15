import { describe, expect, it } from "vitest";

import { GAME_VERSION, pluginInfo } from "./plugin-info.js";

describe("pluginInfo", () => {
  it("reports the plugin id and the pinned game version", () => {
    expect(pluginInfo()).toEqual({ id: "minecraft", gameVersion: GAME_VERSION });
  });
});
