import { PassThrough } from "node:stream";

import { describe, expect, it } from "vitest";

import { ErrorCode, type Handler, JsonRpcServer, RpcError, serveLines } from "./json-rpc.js";

function makeServer(handlers: Record<string, Handler>) {
  const output: unknown[] = [];
  const server = new JsonRpcServer(new Map(Object.entries(handlers)), (line) => {
    output.push(JSON.parse(line));
  });
  return { server, output };
}

describe("JsonRpcServer", () => {
  it("answers a request with the handler result", async () => {
    const { server, output } = makeServer({ add: ({ a, b }) => Number(a) + Number(b) });
    await server.handleLine('{"jsonrpc":"2.0","id":1,"method":"add","params":{"a":2,"b":3}}');
    expect(output).toEqual([{ jsonrpc: "2.0", id: 1, result: 5 }]);
  });

  it("does not answer a notification", async () => {
    let called = false;
    const { server, output } = makeServer({
      ping: () => {
        called = true;
        return null;
      },
    });
    await server.handleLine('{"jsonrpc":"2.0","method":"ping"}');
    expect(called).toBe(true);
    expect(output).toEqual([]);
  });

  it("reports invalid JSON as a parse error", async () => {
    const { server, output } = makeServer({});
    await server.handleLine("{not json");
    expect(output).toEqual([
      { jsonrpc: "2.0", id: null, error: { code: ErrorCode.ParseError, message: "Invalid JSON." } },
    ]);
  });

  it("reports an unknown method", async () => {
    const { server, output } = makeServer({});
    await server.handleLine('{"jsonrpc":"2.0","id":"x","method":"fly"}');
    expect(output).toEqual([
      {
        jsonrpc: "2.0",
        id: "x",
        error: { code: ErrorCode.MethodNotFound, message: "Unknown method: fly" },
      },
    ]);
  });

  it("rejects positional params", async () => {
    const { server, output } = makeServer({ add: () => 0 });
    await server.handleLine('{"jsonrpc":"2.0","id":2,"method":"add","params":[1,2]}');
    expect(output).toMatchObject([{ id: 2, error: { code: ErrorCode.InvalidParams } }]);
  });

  it("passes an RpcError code through and wraps other errors as internal", async () => {
    const { server, output } = makeServer({
      notReady: () => {
        throw new RpcError(ErrorCode.NotReady, "not spawned", { retry: true });
      },
      broken: () => {
        throw new Error("boom");
      },
    });
    await server.handleLine('{"jsonrpc":"2.0","id":1,"method":"notReady"}');
    await server.handleLine('{"jsonrpc":"2.0","id":2,"method":"broken"}');
    expect(output).toEqual([
      {
        jsonrpc: "2.0",
        id: 1,
        error: { code: ErrorCode.NotReady, message: "not spawned", data: { retry: true } },
      },
      { jsonrpc: "2.0", id: 2, error: { code: ErrorCode.InternalError, message: "boom" } },
    ]);
  });

  it("sends notifications", () => {
    const { server, output } = makeServer({});
    server.notify("event", { type: "chat" });
    expect(output).toEqual([{ jsonrpc: "2.0", method: "event", params: { type: "chat" } }]);
  });
});

describe("serveLines", () => {
  it("handles every line until the input closes, concurrently", async () => {
    const order: string[] = [];
    const { server, output } = makeServer({
      slow: async () => {
        await new Promise((resolve) => setTimeout(resolve, 20));
        order.push("slow");
        return "slow";
      },
      fast: () => {
        order.push("fast");
        return "fast";
      },
    });
    const input = new PassThrough();
    const done = serveLines(server, input);
    input.write('{"jsonrpc":"2.0","id":1,"method":"slow"}\n');
    input.write('{"jsonrpc":"2.0","id":2,"method":"fast"}\n');
    input.end();
    await done;
    expect(order).toEqual(["fast", "slow"]);
    expect(output).toHaveLength(2);
  });
});
