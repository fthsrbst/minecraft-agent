/** The broker with fake primitives: real executor processes, no game server. */
import { describe, expect, it } from "vitest";

import { ErrorCode, type JsonObject, type JsonValue, RpcError } from "../rpc/json-rpc.js";
import { type Primitive, SkillBroker } from "./broker.js";
import { syntaxProblem } from "./static-check.js";

function setup(primitives: Record<string, Primitive> = {}) {
  const events: JsonObject[] = [];
  const broker = new SkillBroker(new Map(Object.entries(primitives)), (event) => {
    events.push(event);
  });
  const done = () =>
    new Promise<JsonObject>((resolve) => {
      const check = () => {
        const event = events.find((e) => e.type === "skill.done");
        if (event === undefined) {
          setTimeout(check, 10);
        } else {
          resolve(event);
        }
      };
      check();
    });
  return { broker, events, done };
}

const echo: Primitive = (args) => Promise.resolve({ echoed: args } as JsonValue);

describe("SkillBroker", () => {
  it("runs a skill that calls primitives and returns a value", async () => {
    const { broker, done } = setup({ chat: echo });
    broker.start('const r = await bot.chat("hi"); log("said", r); return { said: r };', {}, 10_000);
    const result = await done();
    expect(result.status).toBe("ok");
    expect(result.result).toEqual({ said: { echoed: { text: "hi" } } });
    expect(result.primitiveCalls).toBe(1);
    expect(result.logs).toEqual(['said {"echoed":{"text":"hi"}}']);
  });

  it("passes args to the skill", async () => {
    const { broker, done } = setup();
    broker.start("return args.count * 2;", { count: 21 }, 10_000);
    expect((await done()).result).toBe(42);
  });

  it("reports a thrown error", async () => {
    const { broker, done } = setup();
    broker.start('throw new Error("no logs nearby");', {}, 10_000);
    const result = await done();
    expect(result.status).toBe("error");
    expect(result.error).toBe("Error: no logs nearby");
  });

  it("turns a primitive failure into an exception inside the skill", async () => {
    const failing: Primitive = () => Promise.reject(new Error("path blocked"));
    const { broker, done } = setup({ goTo: failing });
    broker.start(
      "try { await bot.goTo(1, 2, 3); } catch (e) { return `caught: ${e.message}`; }",
      {},
      10_000,
    );
    expect((await done()).result).toBe("caught: path blocked");
  });

  it("kills an endless synchronous loop", async () => {
    const { broker, done } = setup();
    broker.start("while (true) {}", {}, 1_000);
    const result = await done();
    // The vm guard (5 s) or the broker timeout (1 s) stops it; the broker always wins first here.
    expect(result.status).toBe("timeout");
    expect(broker.runningId).toBeNull();
  });

  it("kills an endless async loop", async () => {
    const { broker, done } = setup({
      wait: () =>
        new Promise((r) =>
          setTimeout(() => {
            r(null);
          }, 5),
        ),
    });
    broker.start("for (;;) { await bot.wait(1); }", {}, 500);
    const result = await done();
    expect(result.status).toBe("timeout");
    expect(Number(result.primitiveCalls)).toBeGreaterThan(0);
  });

  it("cancels a running skill and aborts its primitive", async () => {
    let aborted = false;
    const slow: Primitive = (_args, signal) =>
      new Promise((resolve) => {
        signal.addEventListener("abort", () => {
          aborted = true;
          resolve(null);
        });
      });
    const { broker, done } = setup({ goTo: slow });
    const runId = broker.start("await bot.goTo(0, 0, 0);", {}, 10_000);
    await new Promise((r) => setTimeout(r, 300));
    expect(broker.cancel(runId)).toBe(true);
    expect((await done()).status).toBe("cancelled");
    expect(aborted).toBe(true);
  });

  it("has no process, require or environment inside the skill", async () => {
    const { broker, done } = setup();
    // Written so the static check does not see the names: this tests the sandbox, not the filter.
    broker.start(
      'const g = (function () { return this; })(); return ["pro" + "cess", "req" + "uire", "fetch"].map((n) => typeof g[n]);',
      {},
      10_000,
    );
    expect((await done()).result).toEqual(["undefined", "undefined", "undefined"]);
  });

  it("blocks code generation from strings even when the static check is evaded", async () => {
    const { broker, done } = setup();
    // "Fun" + "ction" passes the text check; the executor's flag still refuses it.
    broker.start(
      'const F = (async () => {})["con" + "structor"]; return F("return 1");',
      {},
      10_000,
    );
    const result = await done();
    expect(result.status).toBe("error");
  });

  it("rejects code the static check can see is forbidden", () => {
    const { broker } = setup();
    expect(() => broker.start("process.exit(0)", {}, 10_000)).toThrow(RpcError);
    expect(() => broker.start('await bot.chat("/op me")', {}, 10_000)).toThrow(/not allowed/);
  });

  it("runs one skill at a time", async () => {
    const { broker, done } = setup({
      wait: () =>
        new Promise((r) =>
          setTimeout(() => {
            r(null);
          }, 200),
        ),
    });
    broker.start("await bot.wait(200);", {}, 10_000);
    try {
      broker.start("return 1;", {}, 10_000);
      expect.unreachable();
    } catch (error) {
      expect((error as RpcError).code).toBe(ErrorCode.NotReady);
    }
    await done();
  });

  it("rejects unknown primitives inside the skill", async () => {
    const { broker, done } = setup();
    broker.start('try { await bot.place("stone"); } catch (e) { return e.message; }', {}, 10_000);
    expect((await done()).result).toBe("unknown primitive place");
  });

  // Regressions from review round 2.

  it("reports `throw undefined` as an error, not a crash", async () => {
    const { broker, done } = setup();
    broker.start("throw undefined;", {}, 10_000);
    const result = await done();
    expect(result.status).toBe("error");
    expect(result.error).toBe("thrown value: undefined");
  });

  it("cannot forge messages through a main-realm prototype", async () => {
    const { broker, done } = setup();
    broker.start(
      'const proto = Object.getPrototypeOf(args); proto.toJSON = () => ({ type: "done", ok: true, result: "forged" }); return "honest";',
      {},
      10_000,
    );
    const result = await done();
    expect(result.result).toBe("honest");
  });

  it("caps the log", async () => {
    const { broker, events, done } = setup();
    broker.start('for (let i = 0; i < 5000; i++) { log("line", i); } return "ok";', {}, 10_000);
    const result = await done();
    expect(result.logs).toHaveLength(100);
    expect(events.filter((e) => e.type === "skill.log")).toHaveLength(100);
  });

  it("refuses a huge result", async () => {
    const { broker, done } = setup();
    broker.start('return "x".repeat(50000);', {}, 10_000);
    const result = await done();
    expect(result.status).toBe("error");
    expect(result.error).toMatch(/larger than/);
  });

  it("ends a run that makes too many primitive calls", async () => {
    const { broker, done } = setup({ wait: () => Promise.resolve(null) });
    broker.start("for (;;) { try { await bot.wait(1); } catch (e) {} }", {}, 30_000);
    const result = await done();
    expect(result.status).toBe("error");
    expect(result.error).toMatch(/more than 500 primitive calls/);
  });

  it("limits chat lines per skill", async () => {
    const { broker, done } = setup({ chat: echo });
    broker.start(
      'let sent = 0; for (let i = 0; i < 30; i++) { try { await bot.chat("x"); sent++; } catch (e) {} } return sent;',
      {},
      10_000,
    );
    expect((await done()).result).toBe(20);
  });

  it("kills a skill whose memory grows outside the JS heap", async () => {
    const { broker, done } = setup();
    broker.start(
      "const chunks = []; for (;;) { chunks.push(new Uint8Array(100_000_000).fill(1)); await null; }",
      {},
      20_000,
    );
    const result = await done();
    expect(result.status).toBe("crashed");
    expect(result.error).toMatch(/memory limit|executor exited/);
  }, 30_000);

  it("does not run calls queued before a cancel", async () => {
    let calls = 0;
    const slow: Primitive = (_args, signal) =>
      new Promise((resolve) => {
        calls += 1;
        signal.addEventListener("abort", () => {
          resolve(null);
        });
      });
    const { broker, done } = setup({ goTo: slow });
    broker.start("await Promise.all([bot.goTo(0,0,0), bot.goTo(1,1,1), bot.goTo(2,2,2)]);", {}, 10_000);
    await new Promise((r) => setTimeout(r, 300));
    broker.cancel();
    await done();
    await new Promise((r) => setTimeout(r, 100));
    expect(calls).toBe(1);
  });

  it("survives a forgotten await on a failing primitive", async () => {
    const failing: Primitive = () => Promise.reject(new Error("no path"));
    const wait: Primitive = (args) =>
      new Promise((resolve) => setTimeout(() => { resolve(null); }, Number(args.ms)));
    const { broker, done } = setup({ goTo: failing, wait });
    broker.start('void bot.goTo(1, 2, 3); await bot.wait(300); return "kept going";', {}, 10_000);
    const result = await done();
    expect(result.status).toBe("ok");
    expect(result.result).toBe("kept going");
    expect(result.logs).toEqual(["unhandled rejection: Error: no path"]);
  });

  it("finds syntax errors without running anything", () => {
    expect(syntaxProblem("return 1;")).toBeNull();
    expect(syntaxProblem("const x = ;")).toMatch(/SyntaxError/);
    expect(syntaxProblem("async function for() {}")).toMatch(/SyntaxError/);
  });
});
