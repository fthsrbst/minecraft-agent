import { describe, expect, it } from "vitest";

import { levelName, parseSeed, WorldError } from "./world.js";

describe("levelName", () => {
  it("maps a seed to a safe directory name", () => {
    expect(levelName(20261119)).toBe("seed20261119");
    expect(levelName(-42)).toBe("seedm42");
    expect(levelName(0)).toBe("seed0");
  });

  it.each([1.5, "../../etc", null, Number.MAX_SAFE_INTEGER + 2, Number.NaN])(
    "rejects %s",
    (seed) => {
      expect(() => parseSeed(seed)).toThrow(WorldError);
    },
  );
});
