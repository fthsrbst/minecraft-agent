/**
 * The primitives the core may request through `act`. Arguments arrive as untrusted JSON (later from
 * L0/L1 decisions), so each one is validated here before it reaches the bot.
 */
import { ErrorCode, type JsonObject, RpcError } from "../rpc/json-rpc.js";

export const MOVE_DIRECTIONS = ["forward", "back", "left", "right"] as const;
export type MoveDirection = (typeof MOVE_DIRECTIONS)[number];

// Long enough to walk a few blocks, short enough that a bad decision cannot run the bot off for long.
export const MAX_MOVE_MS = 5000;
export const MAX_CHAT_LENGTH = 256;

export type Action =
  | { readonly primitive: "chat"; readonly text: string }
  | {
      readonly primitive: "move";
      readonly direction: MoveDirection;
      readonly durationMs: number;
      readonly jump: boolean;
    };

/** What `act` accepts, as JSON Schema; returned by the handshake so the core and the LLM see it. */
export const ACT_PRIMITIVES: JsonObject[] = [
  {
    name: "chat",
    description: "Say a line in game chat. No commands (/) and no control characters.",
    args: {
      type: "object",
      properties: { text: { type: "string", minLength: 1, maxLength: MAX_CHAT_LENGTH } },
      required: ["text"],
      additionalProperties: false,
    },
  },
  {
    name: "move",
    description: "Walk in a direction for a short time (no pathfinding).",
    args: {
      type: "object",
      properties: {
        direction: { enum: [...MOVE_DIRECTIONS] },
        durationMs: { type: "integer", minimum: 1, maximum: MAX_MOVE_MS },
        jump: { type: "boolean" },
      },
      required: ["direction", "durationMs"],
      additionalProperties: false,
    },
  },
];

function invalid(message: string): RpcError {
  return new RpcError(ErrorCode.InvalidParams, message);
}

function isMoveDirection(value: unknown): value is MoveDirection {
  return typeof value === "string" && (MOVE_DIRECTIONS as readonly string[]).includes(value);
}

/** Parses `act` params of the form `{ primitive, args }`. */
export function parseAction(params: JsonObject): Action {
  const { primitive, args = {} } = params;
  if (typeof args !== "object" || args === null || Array.isArray(args)) {
    throw invalid("`args` must be an object.");
  }

  switch (primitive) {
    case "chat": {
      const { text } = args;
      if (typeof text !== "string" || text.trim() === "" || text.length > MAX_CHAT_LENGTH) {
        throw invalid(
          `chat: \`text\` must be a non-empty string of at most ${String(MAX_CHAT_LENGTH)} characters.`,
        );
      }
      // Mineflayer sends each line of a multi-line text as its own message, so "hi\n/op x" would
      // run a command. Control characters are refused outright.
      if (/\p{Cc}/u.test(text)) {
        throw invalid("chat: control characters (including newlines) are not allowed.");
      }
      // The server kicks a player for "§" (formatting codes) and invisible or unassigned characters.
      if (/[§\p{Cf}\p{Co}\p{Cn}\p{Cs}]/u.test(text)) {
        throw invalid("chat: formatting codes (§) and invisible characters are not allowed.");
      }
      // Slash commands are server commands, not chat; the agent never issues them (AGENTS.md decision 8).
      if (text.trimStart().startsWith("/")) {
        throw invalid("chat: commands starting with `/` are not allowed.");
      }
      return { primitive: "chat", text };
    }
    case "move": {
      const { direction, durationMs, jump = false } = args;
      if (!isMoveDirection(direction)) {
        throw invalid(`move: \`direction\` must be one of ${MOVE_DIRECTIONS.join(", ")}.`);
      }
      if (
        typeof durationMs !== "number" ||
        !Number.isInteger(durationMs) ||
        durationMs < 1 ||
        durationMs > MAX_MOVE_MS
      ) {
        throw invalid(`move: \`durationMs\` must be an integer from 1 to ${String(MAX_MOVE_MS)}.`);
      }
      if (typeof jump !== "boolean") {
        throw invalid("move: `jump` must be a boolean.");
      }
      return { primitive: "move", direction, durationMs, jump };
    }
    default:
      throw invalid(`Unknown primitive: ${JSON.stringify(primitive ?? null)}. Known: chat, move.`);
  }
}
