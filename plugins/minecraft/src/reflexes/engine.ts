/**
 * L0 reflex engine: watches game events (no polling), applies the rules in `rules.ts`, and acts at
 * once. An emergency outranks any task (AGENTS.md decision 13), so a reflex first interrupts the
 * running skill or action, then flees, fights or eats, and reports what it did and how fast.
 *
 * Reaction time = from the game event that showed the danger to the first action sent to the
 * server (a movement goal or an attack). The target is ≤ 100 ms (decision 10).
 */
import type { Bot } from "mineflayer";
import type { Entity } from "prismarine-entity";
import pathfinderModule from "mineflayer-pathfinder";

import type { JsonObject } from "../rpc/json-rpc.js";
import { chooseReflex, type ReflexChoice, type Threat } from "./rules.js";

const { goals } = pathfinderModule;

const WATCH_RADIUS = 16;
const SAFE_DISTANCE = 16;
const FLEE_MAX_MS = 8_000;
const FIGHT_MAX_MS = 30_000;
// Feet-to-feet distance; the game's reach (about 3 blocks from the eyes to the hitbox) allows this.
const ATTACK_REACH = 3.5;
// Vanilla attack cooldowns: swords recharge in 0.625 s, axes in about 1 s, fists in 0.25 s.
const COOLDOWN_MS: Readonly<Record<string, number>> = { sword: 625, axe: 1_000 };
const FIST_COOLDOWN_MS = 250;
const EVALUATE_MIN_GAP_MS = 50;
const EAT_MAX_MS = 5_000;
const SURFACE_MAX_MS = 10_000;
// After a reflex fails (no food, a fight that timed out), the same kind waits before it retries,
// so a hopeless reflex cannot keep interrupting the task every tick.
const FAILED_COOLDOWN_MS = 5_000;
// Hostile mobs that minecraft-data does not type as "hostile" in every version.
const EXTRA_HOSTILE: ReadonlySet<string> = new Set([
  "slime",
  "magma_cube",
  "phantom",
  "ghast",
  "hoglin",
  "shulker",
]);
// Weapons by preference (best first).
const WEAPONS = [
  "netherite_sword",
  "diamond_sword",
  "iron_sword",
  "stone_sword",
  "golden_sword",
  "wooden_sword",
  "netherite_axe",
  "diamond_axe",
  "iron_axe",
  "stone_axe",
  "golden_axe",
  "wooden_axe",
];
// Food by preference: cooked and filling first; never anything that poisons.
const FOODS = [
  "cooked_beef",
  "cooked_porkchop",
  "cooked_mutton",
  "cooked_chicken",
  "cooked_salmon",
  "baked_potato",
  "bread",
  "cooked_cod",
  "carrot",
  "apple",
  "melon_slice",
  "sweet_berries",
  "beef",
  "porkchop",
  "mutton",
];

export interface ReflexHooks {
  /** Stops the running skill or action because of this reflex; true if something was stopped. */
  readonly interruptWork: (reason: string) => boolean;
  /** True while a skill or an action is running. */
  readonly working: () => boolean;
  readonly emit: (event: JsonObject) => void;
}

export class ReflexEngine {
  private active: Promise<void> | null = null;
  private lastEvaluation = 0;
  private enabled = true;
  private readonly cooldownUntil = new Map<ReflexChoice["kind"], number>();

  constructor(
    private readonly bot: Bot,
    private readonly hooks: ReflexHooks,
  ) {
    const onEvent = (): void => {
      this.evaluate(performance.now());
    };
    bot.on("entityMoved", onEvent);
    bot.on("entitySpawn", onEvent);
    bot.on("health", onEvent);
    bot.on("breath", onEvent);
  }

  get busy(): boolean {
    return this.active !== null;
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  /** Runs on game events; `triggeredAt` is when the event arrived, for the reaction time. */
  evaluate(triggeredAt: number): void {
    // A dead or not yet respawned bot has no position to flee from and nothing to fight with.
    if (!this.enabled || this.active !== null || !hasEntity(this.bot)) {
      return;
    }
    if (this.bot.health <= 0) {
      return;
    }
    // entityMoved fires many times per tick; the rules need not run that often.
    if (triggeredAt - this.lastEvaluation < EVALUATE_MIN_GAP_MS) {
      return;
    }
    this.lastEvaluation = triggeredAt;
    const choice = this.choose();
    if (choice === null || (this.cooldownUntil.get(choice.kind) ?? 0) > triggeredAt) {
      return;
    }
    this.active = this.respond(choice, triggeredAt)
      .catch((error: unknown) => {
        console.error("reflex failed:", error);
      })
      .finally(() => {
        this.active = null;
      });
  }

  private choose(): ReflexChoice | null {
    return chooseReflex({
      health: this.bot.health,
      food: this.bot.food,
      oxygen: this.bot.oxygenLevel,
      threats: this.threats(),
      hasWeapon: this.weapon() !== null,
      hasFood: this.food() !== null,
      working: this.hooks.working(),
    });
  }

  private threats(): Threat[] {
    const origin = this.bot.entity.position;
    return Object.values(this.bot.entities)
      .filter(
        (entity) =>
          entity.isValid &&
          (entity.type === "hostile" || EXTRA_HOSTILE.has(entity.name ?? "")) &&
          entity !== this.bot.entity,
      )
      .map((entity) => ({
        id: entity.id,
        name: entity.name ?? "unknown",
        distance: entity.position.distanceTo(origin),
      }))
      .filter((threat) => threat.distance <= WATCH_RADIUS);
  }

  private weapon(): string | null {
    const names = new Set(this.bot.inventory.items().map((item) => item.name));
    return WEAPONS.find((name) => names.has(name)) ?? null;
  }

  private food(): string | null {
    const names = new Set(this.bot.inventory.items().map((item) => item.name));
    return FOODS.find((name) => names.has(name)) ?? null;
  }

  private async respond(choice: ReflexChoice, triggeredAt: number): Promise<void> {
    const started = performance.now();
    const interrupted =
      choice.kind === "eat" && !this.hooks.working()
        ? false
        : this.hooks.interruptWork(`reflex ${choice.kind}: ${choice.reason}`);
    let reactionMs: number | null = null;
    const acted = (): void => {
      if (reactionMs !== null) {
        return;
      }
      reactionMs = Math.round((performance.now() - triggeredAt) * 10) / 10;
      // The core waits for the reflex to finish before resuming work; this says one has begun.
      this.hooks.emit({ type: "reflex.started", reflex: choice.kind, reactionMs });
    };
    let outcome: string;
    try {
      outcome =
        choice.kind === "flee"
          ? await this.flee(choice.target, acted)
          : choice.kind === "fight"
            ? await this.fight(choice.target, acted)
            : choice.kind === "surface"
              ? await this.surface(acted)
              : await this.eat(acted);
    } catch (error: unknown) {
      outcome = `failed: ${error instanceof Error ? error.message : String(error)}`;
    } finally {
      try {
        this.bot.pathfinder.setGoal(null);
        this.bot.clearControlStates();
      } catch {
        // The bot died or disconnected during the reflex; there is nothing left to stop.
      }
    }
    if (/^(failed|no food|fight timed out)/.test(outcome)) {
      this.cooldownUntil.set(choice.kind, performance.now() + FAILED_COOLDOWN_MS);
    }
    this.hooks.emit({
      type: "reflex",
      reflex: choice.kind,
      reason: choice.reason,
      ...(choice.kind === "flee" || choice.kind === "fight" ? { target: choice.target.name } : {}),
      interruptedWork: interrupted,
      reactionMs,
      durationMs: Math.round(performance.now() - started),
      outcome,
      health: this.bot.health,
      food: this.bot.food,
    });
  }

  /** The rules again, mid-fight: a creeper or a pack arriving turns the fight into a flight. */
  private fleeInstead(): Extract<ReflexChoice, { kind: "flee" }> | null {
    const choice = this.choose();
    return choice?.kind === "flee" ? choice : null;
  }

  private entity(id: number): Entity | null {
    const entity = this.bot.entities[id];
    return entity?.isValid ? entity : null;
  }

  private async flee(target: Threat, acted: () => void): Promise<string> {
    const threat = this.entity(target.id);
    if (threat === null) {
      return "threat gone";
    }
    this.bot.pathfinder.setGoal(
      new goals.GoalInvert(new goals.GoalFollow(threat, SAFE_DISTANCE)),
      true,
    );
    acted();
    const deadline = performance.now() + FLEE_MAX_MS;
    while (performance.now() < deadline) {
      await sleep(200);
      const current = this.entity(target.id);
      if (
        current === null ||
        current.position.distanceTo(this.bot.entity.position) >= SAFE_DISTANCE
      ) {
        return "escaped";
      }
    }
    return "still close after fleeing";
  }

  private async fight(target: Threat, acted: () => void): Promise<string> {
    const weapon = this.weapon();
    if (weapon !== null) {
      const item = this.bot.inventory.items().find((stack) => stack.name === weapon);
      if (item !== undefined) {
        // Equipping is a round trip; the first attack must not wait for it.
        void this.bot.equip(item, "hand").catch(() => undefined);
      }
    }
    const cooldown =
      weapon === null
        ? FIST_COOLDOWN_MS
        : (COOLDOWN_MS[weapon.endsWith("_axe") ? "axe" : "sword"] ?? 625);
    const deadline = performance.now() + FIGHT_MAX_MS;
    let lastAttack = 0;
    while (performance.now() < deadline) {
      const enemy = this.entity(target.id);
      if (enemy === null) {
        return "threat defeated or gone";
      }
      const flee = this.fleeInstead();
      if (flee !== null) {
        return `switched to flee (${flee.reason}): ${await this.flee(flee.target, acted)}`;
      }
      const distance = enemy.position.distanceTo(this.bot.entity.position);
      if (distance > ATTACK_REACH) {
        this.bot.pathfinder.setGoal(new goals.GoalFollow(enemy, 2), true);
        acted();
      } else if (performance.now() - lastAttack >= cooldown) {
        this.bot.pathfinder.setGoal(null);
        await this.bot.lookAt(enemy.position.offset(0, enemy.height * 0.85, 0), true);
        this.bot.attack(enemy);
        acted();
        lastAttack = performance.now();
      }
      await sleep(50);
    }
    return "fight timed out";
  }

  /** Holds jump (swim up) until the air is full again; a ceiling of rock defeats this. */
  private async surface(acted: () => void): Promise<string> {
    this.bot.pathfinder.setGoal(null);
    this.bot.setControlState("jump", true);
    acted();
    const deadline = performance.now() + SURFACE_MAX_MS;
    while (performance.now() < deadline) {
      await sleep(200);
      if (this.bot.oxygenLevel >= 20) {
        return "surfaced";
      }
    }
    return `failed: still under water (air ${String(this.bot.oxygenLevel)})`;
  }

  private async eat(acted: () => void): Promise<string> {
    const food = this.food();
    const item = this.bot.inventory.items().find((stack) => stack.name === food);
    if (item === undefined) {
      return "no food";
    }
    await this.bot.equip(item, "hand");
    acted();
    // consume() never settles if the server does not confirm (e.g. the item was taken mid-use).
    let timer: NodeJS.Timeout | undefined;
    const timedOut = new Promise<false>((resolve) => {
      timer = setTimeout(() => {
        resolve(false);
      }, EAT_MAX_MS);
    });
    try {
      const ate = await Promise.race([this.bot.consume().then(() => true), timedOut]);
      if (!ate) {
        this.bot.deactivateItem();
        return "failed: eating timed out";
      }
    } finally {
      clearTimeout(timer);
    }
    return `ate ${item.name}`;
  }
}

// Mineflayer types `bot.entity` as always set, but it is undefined before spawn and after an end.
function hasEntity(bot: Bot): boolean {
  return (bot.entity as Entity | undefined) !== undefined;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
