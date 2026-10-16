/**
 * Messages between the skill broker (plugin process, owns the bot) and the skill executor (a child
 * process that runs untrusted skill code and owns nothing). Sent over Node's IPC channel as JSON.
 */
import type { JsonObject, JsonValue } from "../rpc/json-rpc.js";

/** broker → executor: start the code once. */
export interface RunMessage {
  readonly type: "run";
  readonly code: string;
  readonly args: JsonObject;
}

/** broker → executor: the answer to one primitive call. */
export interface ReplyMessage {
  readonly type: "reply";
  readonly id: number;
  readonly ok: boolean;
  readonly value?: JsonValue;
  readonly error?: string;
}

/** executor → broker: ask the broker to run a primitive. */
export interface CallMessage {
  readonly type: "call";
  readonly id: number;
  readonly name: string;
  readonly args: JsonObject;
}

export interface LogMessage {
  readonly type: "log";
  readonly message: string;
}

/** executor → broker: the skill finished (returned or threw). */
export interface DoneMessage {
  readonly type: "done";
  readonly ok: boolean;
  readonly result?: JsonValue;
  readonly error?: string;
}

export type ToExecutor = RunMessage | ReplyMessage;
export type FromExecutor = CallMessage | LogMessage | DoneMessage;
