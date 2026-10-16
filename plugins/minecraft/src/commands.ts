/**
 * The #command vocabulary (plan P3.2). Commands are declared in commands/commands.json; a command
 * either names a skill file (run through the skill executor like any skill, so cancel, reflexes
 * and timeouts work the same) or a builtin the core handles itself (stop, places, help).
 */
import { readFileSync } from "node:fs";

import type { JsonObject } from "./rpc/json-rpc.js";

const NAME = /^[a-z][a-z0-9_]{0,23}$/;
const ARG_TYPES = new Set(["word", "int", "number", "position", "player"]);

export class CommandsError extends Error {
  override readonly name = "CommandsError";
}

/** Reads commands.json and inlines each command's skill code; fails at startup on a bad file. */
export function loadCommands(directory: URL): JsonObject {
  const raw = JSON.parse(readFileSync(new URL("commands.json", directory), "utf8")) as unknown;
  if (typeof raw !== "object" || raw === null || !("commands" in raw)) {
    throw new CommandsError("commands.json must have a `commands` list");
  }
  const { prefix = "#", commands } = raw as { prefix?: unknown; commands: unknown };
  if (typeof prefix !== "string" || prefix.length !== 1 || !Array.isArray(commands)) {
    throw new CommandsError("commands.json: `prefix` must be one character, `commands` a list");
  }
  const loaded = commands.map((entry: unknown): JsonObject => {
    if (typeof entry !== "object" || entry === null) {
      throw new CommandsError("each command must be an object");
    }
    const command = entry as Record<string, unknown>;
    const { name, usage, description, args, skill, builtin } = command;
    if (typeof name !== "string" || !NAME.test(name)) {
      throw new CommandsError(`bad command name ${JSON.stringify(name)}`);
    }
    if (typeof usage !== "string" || typeof description !== "string" || !Array.isArray(args)) {
      throw new CommandsError(`${name}: usage, description and args are required`);
    }
    for (const arg of args as unknown[]) {
      const type = (arg as { type?: unknown } | null)?.type;
      if (typeof type !== "string" || !ARG_TYPES.has(type)) {
        throw new CommandsError(`${name}: unknown argument type ${JSON.stringify(type)}`);
      }
    }
    if ((skill === undefined) === (builtin === undefined)) {
      throw new CommandsError(`${name}: exactly one of skill or builtin`);
    }
    const base: JsonObject = { name, usage, description, args: args as JsonObject[] };
    if (typeof skill === "string") {
      return { ...base, code: readFileSync(new URL(skill, directory), "utf8") };
    }
    return { ...base, builtin: String(builtin) };
  });
  return { prefix, commands: loaded };
}
