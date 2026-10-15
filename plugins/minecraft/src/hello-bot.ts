/**
 * P1.2 hello bot: joins the local server, greets once, and answers chat lines that mention it.
 * Run with `npm run hello` while `docker compose up` is running.
 */
import { createBot } from "mineflayer";

import { loadBotConfig } from "./bot-config.js";
import { replyTo } from "./chat-reply.js";
import { GAME_VERSION } from "./plugin-info.js";

const config = loadBotConfig(process.env);
console.log(
  `Connecting ${config.username} to ${config.host}:${String(config.port)} (${GAME_VERSION})…`,
);

const bot = createBot({
  host: config.host,
  port: config.port,
  username: config.username,
  // Offline mode: no Microsoft login (the server is localhost-only, AGENTS.md decision 4).
  auth: "offline",
  version: GAME_VERSION,
});

bot.once("spawn", () => {
  const { x, y, z } = bot.entity.position;
  console.log(`Spawned at ${x.toFixed(1)} ${y.toFixed(1)} ${z.toFixed(1)}`);
  bot.chat(`Hello! I am ${bot.username}. Mention my name and I will answer.`);
});

bot.on("chat", (sender, message) => {
  const reply = replyTo(sender, message, bot.username);
  if (reply !== null) {
    bot.chat(reply);
  }
});

bot.on("kicked", (reason) => {
  console.error(`Kicked: ${JSON.stringify(reason)}`);
  process.exitCode = 1;
});

bot.on("error", (error) => {
  console.error(`Connection error: ${error.message}`);
  process.exitCode = 1;
});

bot.on("end", (reason) => {
  console.log(`Disconnected: ${reason}`);
});

process.once("SIGINT", () => {
  bot.quit("shutting down");
});
