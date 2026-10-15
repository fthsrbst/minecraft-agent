/** Connection settings for the bot, read from the environment. */
export interface BotConfig {
  readonly host: string;
  readonly port: number;
  readonly username: string;
}

// The bot runs LLM-written code, so it may only ever join the local Docker server (AGENTS.md security rule).
const LOCAL_HOSTS: ReadonlySet<string> = new Set(["localhost", "127.0.0.1", "::1"]);

// Minecraft usernames: 3–16 characters, letters, digits and underscore.
const USERNAME_PATTERN = /^\w{3,16}$/;

export class BotConfigError extends Error {
  override readonly name = "BotConfigError";
}

export function loadBotConfig(env: NodeJS.ProcessEnv): BotConfig {
  const host = env.MC_HOST ?? "127.0.0.1";
  if (!LOCAL_HOSTS.has(host)) {
    throw new BotConfigError(
      `MC_HOST=${host} is not allowed: the bot may only join a local server (${[...LOCAL_HOSTS].join(", ")}).`,
    );
  }

  const rawPort = env.MC_PORT ?? "25565";
  const port = Number(rawPort);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new BotConfigError(`MC_PORT=${rawPort} is not a valid TCP port.`);
  }

  const username = env.MC_USERNAME ?? "AgentBot";
  if (!USERNAME_PATTERN.test(username)) {
    throw new BotConfigError(
      `MC_USERNAME=${username} is not a valid Minecraft username (3–16 letters, digits or _).`,
    );
  }

  return { host, port, username };
}
