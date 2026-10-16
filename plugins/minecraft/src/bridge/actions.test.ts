import { describe, expect, it } from "vitest";

import { ErrorCode, type JsonObject, RpcError } from "../rpc/json-rpc.js";
import { MAX_MOVE_MS, parseAction } from "./actions.js";

function expectInvalid(params: JsonObject, message: RegExp): void {
  try {
    parseAction(params);
  } catch (error) {
    expect(error).toBeInstanceOf(RpcError);
    expect((error as RpcError).code).toBe(ErrorCode.InvalidParams);
    expect((error as RpcError).message).toMatch(message);
    return;
  }
  throw new Error("expected parseAction to throw");
}

describe("parseAction", () => {
  it("parses chat", () => {
    expect(parseAction({ primitive: "chat", args: { text: "hello" } })).toEqual({
      primitive: "chat",
      text: "hello",
    });
  });

  it("parses move with jump defaulting to false", () => {
    expect(
      parseAction({ primitive: "move", args: { direction: "forward", durationMs: 500 } }),
    ).toEqual({ primitive: "move", direction: "forward", durationMs: 500, jump: false });
  });

  it.each<[string, JsonObject, RegExp]>([
    ["slash command", { primitive: "chat", args: { text: " /op AgentBot" } }, /not allowed/],
    [
      "command after a newline",
      { primitive: "chat", args: { text: "hi\n/me bypass" } },
      /control characters/,
    ],
    ["carriage return", { primitive: "chat", args: { text: "hi\r/op x" } }, /control characters/],
    ["formatting code", { primitive: "chat", args: { text: "hello §kfoo" } }, /formatting codes/],
    ["zero-width space", { primitive: "chat", args: { text: "a\u200bb" } }, /invisible/],
    ["empty chat", { primitive: "chat", args: { text: "  " } }, /non-empty/],
    ["long chat", { primitive: "chat", args: { text: "a".repeat(257) } }, /at most 256/],
    [
      "bad direction",
      { primitive: "move", args: { direction: "up", durationMs: 100 } },
      /direction/,
    ],
    [
      "zero duration",
      { primitive: "move", args: { direction: "left", durationMs: 0 } },
      /durationMs/,
    ],
    [
      "too long",
      { primitive: "move", args: { direction: "left", durationMs: MAX_MOVE_MS + 1 } },
      /durationMs/,
    ],
    [
      "fractional",
      { primitive: "move", args: { direction: "left", durationMs: 1.5 } },
      /durationMs/,
    ],
    [
      "jump type",
      { primitive: "move", args: { direction: "back", durationMs: 9, jump: 1 } },
      /jump/,
    ],
    ["args type", { primitive: "chat", args: [] }, /args/],
    ["unknown", { primitive: "fly", args: {} }, /Unknown primitive: "fly"/],
    ["missing", {}, /Unknown primitive: null/],
  ])("rejects %s", (_name, params, message) => {
    expectInvalid(params, message);
  });
});
