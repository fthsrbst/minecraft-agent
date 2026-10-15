/**
 * Newline-delimited JSON-RPC 2.0: one JSON message per line. Game-independent; the Minecraft
 * specifics live in the handlers passed to `JsonRpcServer`.
 */
import { createInterface } from "node:readline";

export type JsonValue =
  string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = Record<string, JsonValue>;
export type RequestId = string | number;

/** Standard JSON-RPC 2.0 error codes, plus our application range (-32000 to -32099). */
export const ErrorCode = {
  ParseError: -32700,
  InvalidRequest: -32600,
  MethodNotFound: -32601,
  InvalidParams: -32602,
  InternalError: -32603,
  /** The game is not in a state where the method can run (e.g. the bot has not spawned). */
  NotReady: -32001,
} as const;

/** Throw from a handler to send a specific error code to the caller. */
export class RpcError extends Error {
  override readonly name = "RpcError";

  constructor(
    readonly code: number,
    message: string,
    readonly data?: JsonValue,
  ) {
    super(message);
  }
}

export type Handler = (params: JsonObject) => Promise<JsonValue> | JsonValue;

interface Request {
  readonly id: RequestId | null;
  readonly method: string;
  readonly params: JsonObject;
}

function isJsonObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Validates one decoded message; returns a request or an RpcError explaining why it is not one. */
export function parseRequest(message: unknown): Request | RpcError {
  if (!isJsonObject(message) || message.jsonrpc !== "2.0") {
    return new RpcError(ErrorCode.InvalidRequest, "Not a JSON-RPC 2.0 message.");
  }
  const { id, method, params } = message;
  if (id !== undefined && typeof id !== "string" && typeof id !== "number") {
    return new RpcError(ErrorCode.InvalidRequest, "`id` must be a string or a number.");
  }
  if (typeof method !== "string" || method === "") {
    return new RpcError(ErrorCode.InvalidRequest, "`method` must be a non-empty string.");
  }
  if (params !== undefined && !isJsonObject(params)) {
    return new RpcError(ErrorCode.InvalidParams, "`params` must be an object (named parameters).");
  }
  return { id: id ?? null, method, params: params ?? {} };
}

export class JsonRpcServer {
  constructor(
    private readonly handlers: ReadonlyMap<string, Handler>,
    private readonly writeLine: (line: string) => void,
  ) {}

  /** Handles one input line; a request gets exactly one response, a notification (no id) gets none. */
  async handleLine(line: string): Promise<void> {
    if (line.trim() === "") {
      return;
    }
    let message: unknown;
    try {
      message = JSON.parse(line);
    } catch {
      this.sendError(null, new RpcError(ErrorCode.ParseError, "Invalid JSON."));
      return;
    }

    const request = parseRequest(message);
    if (request instanceof RpcError) {
      const id = isJsonObject(message) ? message.id : undefined;
      this.sendError(typeof id === "string" || typeof id === "number" ? id : null, request);
      return;
    }

    const handler = this.handlers.get(request.method);
    if (handler === undefined) {
      if (request.id !== null) {
        this.sendError(
          request.id,
          new RpcError(ErrorCode.MethodNotFound, `Unknown method: ${request.method}`),
        );
      }
      return;
    }

    try {
      const result = await handler(request.params);
      if (request.id !== null) {
        this.send({ jsonrpc: "2.0", id: request.id, result });
      }
    } catch (error: unknown) {
      if (request.id === null) {
        return;
      }
      const rpcError =
        error instanceof RpcError
          ? error
          : new RpcError(
              ErrorCode.InternalError,
              error instanceof Error ? error.message : String(error),
            );
      this.sendError(request.id, rpcError);
    }
  }

  /** Sends a server-to-client notification (used for the game event stream). */
  notify(method: string, params: JsonObject): void {
    this.send({ jsonrpc: "2.0", method, params });
  }

  private sendError(id: RequestId | null, error: RpcError): void {
    const body: JsonObject = { code: error.code, message: error.message };
    if (error.data !== undefined) {
      body.data = error.data;
    }
    this.send({ jsonrpc: "2.0", id, error: body });
  }

  private send(message: JsonObject): void {
    this.writeLine(JSON.stringify(message));
  }
}

/**
 * Reads requests line by line from `input` until it closes. Requests are handled concurrently,
 * so a slow `act` does not block an `observe`; responses carry the id, so order does not matter.
 */
export async function serveLines(
  server: JsonRpcServer,
  input: NodeJS.ReadableStream,
): Promise<void> {
  const lines = createInterface({ input, crlfDelay: Infinity });
  const inFlight = new Set<Promise<void>>();
  for await (const line of lines) {
    const task = server.handleLine(line).finally(() => inFlight.delete(task));
    inFlight.add(task);
  }
  await Promise.all(inFlight);
}
