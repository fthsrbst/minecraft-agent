/**
 * Fresh worlds per seed for reproducible evaluation (AGENTS.md decision 14: learning seeds differ
 * from test seeds; the world is restored before every run).
 *
 * The first request for a seed generates the world and stores a pristine copy. Every request then
 * stops the server, restores that copy, and starts the server again with that level, so no block a
 * previous run mined or placed survives. The bot reconnects with a new handshake afterwards.
 */
import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { cp, mkdir, rename, rm, stat } from "node:fs/promises";
import { join } from "node:path";
import { promisify } from "node:util";

const run = promisify(execFile);

const COMPOSE_TIMEOUT_MS = 120_000;
const HEALTH_TIMEOUT_MS = 240_000;
const HEALTH_POLL_MS = 2_000;
const MAX_SEED = Number.MAX_SAFE_INTEGER;

export interface WorldConfig {
  /** Directory with docker-compose.yml; world data lives in its data/ folder. */
  readonly composeDir: string;
  readonly service: string;
  readonly container: string;
}

export interface FreshWorld {
  readonly worldInstanceId: string;
  readonly level: string;
  readonly seed: number;
  /** True when this call generated the world for the first time. */
  readonly generated: boolean;
  readonly durationMs: number;
}

export class WorldError extends Error {
  override readonly name = "WorldError";
}

/** The seed reaches a directory name and a server setting, so only safe integers pass. */
export function parseSeed(seed: unknown): number {
  if (typeof seed !== "number" || !Number.isInteger(seed) || Math.abs(seed) > MAX_SEED) {
    throw new WorldError("`seed` must be an integer.");
  }
  return seed;
}

export function levelName(seed: number): string {
  return `seed${seed < 0 ? "m" : ""}${String(Math.abs(seed))}`;
}

async function exists(path: string): Promise<boolean> {
  try {
    await stat(path);
    return true;
  } catch {
    return false;
  }
}

let composeCommand: readonly string[] | null = null;

/** `docker compose` (plugin) when it works, else the standalone `docker-compose`. */
async function detectCompose(): Promise<readonly string[]> {
  if (composeCommand !== null) {
    return composeCommand;
  }
  try {
    await run("docker", ["compose", "version"], { timeout: 10_000 });
    composeCommand = ["docker", "compose"];
  } catch {
    composeCommand = ["docker-compose"];
  }
  return composeCommand;
}

async function compose(
  config: WorldConfig,
  args: readonly string[],
  env: NodeJS.ProcessEnv,
): Promise<void> {
  const [command = "docker-compose", ...prefix] = await detectCompose();
  try {
    await run(command, [...prefix, ...args], {
      cwd: config.composeDir,
      env,
      timeout: COMPOSE_TIMEOUT_MS,
    });
  } catch (error: unknown) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new WorldError(`${command} ${[...prefix, ...args].join(" ")} failed: ${detail}`);
  }
}

async function waitHealthy(config: WorldConfig): Promise<void> {
  const deadline = Date.now() + HEALTH_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const { stdout } = await run(
        "docker",
        ["inspect", "-f", "{{.State.Health.Status}}", config.container],
        { timeout: 10_000 },
      );
      if (stdout.trim() === "healthy") {
        return;
      }
    } catch {
      // The container may not exist yet while it is being recreated.
    }
    await new Promise((resolve) => setTimeout(resolve, HEALTH_POLL_MS));
  }
  throw new WorldError(
    `${config.container} was not healthy within ${String(HEALTH_TIMEOUT_MS / 1000)} s.`,
  );
}

export async function freshWorld(
  config: WorldConfig,
  rawSeed: unknown,
  baseEnv: NodeJS.ProcessEnv,
): Promise<FreshWorld> {
  const started = Date.now();
  const seed = parseSeed(rawSeed);
  const level = levelName(seed);
  const live = join(config.composeDir, "data", "server", level);
  const pristine = join(config.composeDir, "data", "pristine", level);
  // docker-compose.yml reads MC_LEVEL and MC_SEED; a changed value recreates the container.
  const env = { ...baseEnv, MC_LEVEL: level, MC_SEED: String(seed) };

  let generated = false;
  // A pristine copy counts only once it is complete (level.dat exists): the copy is made into a
  // temporary folder and renamed, so an interrupted first run never leaves a half world behind.
  if (!(await exists(join(pristine, "level.dat")))) {
    await rm(pristine, { recursive: true, force: true });
    await compose(config, ["stop", config.service], env);
    await rm(live, { recursive: true, force: true });
    await compose(config, ["up", "-d", config.service], env);
    await waitHealthy(config);
    // Stopping saves every chunk to disk before the copy is taken.
    await compose(config, ["stop", config.service], env);
    if (!(await exists(join(live, "level.dat")))) {
      throw new WorldError(`the server did not write ${level}/level.dat; generation failed`);
    }
    const partial = `${pristine}.partial`;
    await mkdir(join(config.composeDir, "data", "pristine"), { recursive: true });
    await rm(partial, { recursive: true, force: true });
    await cp(live, partial, { recursive: true });
    await rename(partial, pristine);
    generated = true;
  }

  await compose(config, ["stop", config.service], env);
  await rm(live, { recursive: true, force: true });
  await cp(pristine, live, { recursive: true });
  await compose(config, ["up", "-d", config.service], env);
  await waitHealthy(config);

  return {
    worldInstanceId: `${level}-${randomUUID().slice(0, 8)}`,
    level,
    seed,
    generated,
    durationMs: Date.now() - started,
  };
}
