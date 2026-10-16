/**
 * A scripted demonstrator for testing record a skill (P4.1) without a human at the keyboard: a
 * second player that asks the agent to record, builds a 3×3 floor in front of itself with `//`
 * notes, and stops the recording. A real player does the same with the vanilla client.
 *
 *   node dist/tools/teacher.js [--name Teacher] [--block oak_planks] [--skill floor]
 *
 * The teacher must already hold 9 of the block and stand on flat, open ground (the evaluator's
 * scenario setup does both by RCON). Local server only: it connects to MC_HOST/MC_PORT.
 */
import { createBot } from "mineflayer";
import { Vec3 } from "vec3";

import { loadBotConfig } from "../bot-config.js";
import { GAME_VERSION } from "../plugin-info.js";

function option(name: string, fallback: string): string {
  const index = process.argv.indexOf(`--${name}`);
  return index >= 0 ? (process.argv[index + 1] ?? fallback) : fallback;
}

const name = option("name", "Teacher");
const block = option("block", "oak_planks");
const skill = option("skill", "floor");
const config = loadBotConfig({ ...process.env, MC_USERNAME: name });
const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

const bot = createBot({
  host: config.host,
  port: config.port,
  username: name,
  auth: "offline",
  version: GAME_VERSION,
});
bot.on("messagestr", (message) => {
  console.log(`chat: ${message}`);
});
bot.on("error", (error) => {
  console.error(`error: ${error.message}`);
  process.exitCode = 1;
});

bot.once("spawn", () => {
  void (async () => {
    await bot.waitForChunksToLoad();
    await sleep(2_000);
    const stack = bot.inventory.items().find((item) => item.name === block);
    if (stack === undefined || stack.count < 9) {
      throw new Error(`the teacher needs 9 ${block}; give them by RCON first`);
    }
    await bot.look(0, 0, true); // face north: the floor goes to -z
    bot.chat("#record start");
    await sleep(3_000);
    bot.chat("// a 3x3 floor right in front of me, built row by row");
    await bot.equip(stack, "hand");
    const feet = bot.entity.position.floored();
    for (let c = 1; c <= 3; c++) {
      for (let a = -1; a <= 1; a++) {
        const ground = bot.blockAt(new Vec3(feet.x + a, feet.y - 1, feet.z - c));
        if (ground === null) {
          throw new Error("the ground in front of the teacher is not loaded");
        }
        await bot.placeBlock(ground, new Vec3(0, 1, 0));
        await sleep(300);
      }
    }
    bot.chat("// done; it needs flat ground");
    await sleep(1_500);
    bot.chat(`#record stop ${skill}`);
    await sleep(20_000);
    bot.quit("demonstration done");
  })().catch((error: unknown) => {
    console.error(`teacher failed: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
    bot.quit("failed");
  });
});
