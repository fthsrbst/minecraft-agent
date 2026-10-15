import { describe, expect, it } from "vitest";

import { replyTo } from "./chat-reply.js";

describe("replyTo", () => {
  it("answers a message that mentions the bot, case-insensitively", () => {
    expect(replyTo("Fatih", "hey agentbot, are you there? ", "AgentBot")).toBe(
      'Hi Fatih! I am AgentBot, a learning agent. I heard you say: "hey agentbot, are you there?"',
    );
  });

  it("ignores messages that do not mention the bot", () => {
    expect(replyTo("Fatih", "nice weather", "AgentBot")).toBeNull();
  });

  it("never answers its own messages", () => {
    expect(replyTo("AgentBot", "I am AgentBot", "AgentBot")).toBeNull();
  });
});
