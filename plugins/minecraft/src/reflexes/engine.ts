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
  }

  get busy(): boolean {
    return this.active !== null;
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  /** Runs on game events; `triggeredAt` is when the event arrived, for the reaction time. */
  evaluate(triggeredAt: number): void {
    if (!this.enabled || this.active !== null) {
      return;
    }
    // entityMoved fires many times per tick; the rules need not run that often.
    if (triggeredAt - this.lastEvaluation < EVALUATE_MIN_GAP_MS) {
      return;
    }
    this.lastEvaluation = triggeredAt;
    const choice = chooseReflex({
      health: this.bot.health,
      food: this.bot.food,
      threats: this.threats(),
      hasWeapon: this.weapon() !== null,
      hasFood: this.food() !== null,
      working: this.hooks.working(),
    });
    if (choice === null) {
      return;
    }
    this.active = this.respond(choice, triggeredAt).finally(() => {
      this.active = null;
    });
  }

  private threats(): Threat[] {
    const origin = this.bot.entity.position;
    return Object.values(this.bot.entities)
      .filter((entity) => entity.type === "hostile" && entity.isValid)
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
      reactionMs ??= Math.round((performance.now() - triggeredAt) * 10) / 10;
    };
    let outcome: string;
    try {
      outcome =
        choice.kind === "flee"
          ? await this.flee(choice.target, acted)
          : choice.kind === "fight"
            ? await this.fight(choice.target, acted)
            : await this.eat(acted);
    } catch (error: unknown) {
      outcome = `failed: ${error instanceof Error ? error.message : String(error)}`;
    } finally {
      this.bot.pathfinder.setGoal(null);
      this.bot.clearControlStates();
    }
    this.hooks.emit({
      type: "reflex",
      reflex: choice.kind,
      reason: choice.reason,
      ...(choice.kind === "eat" ? {} : { target: choice.target.name }),
      interruptedWork: interrupted,
      reactionMs,
      durationMs: Math.round(performance.now() - started),
      outcome,
      health: this.bot.health,
      food: this.bot.food,
    });
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
      if (this.bot.health < 6) {
        return `switched to flee: ${await this.flee(target, acted)}`;
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

  private async eat(acted: () => void): Promise<string> {
    const food = this.food();
    const item = this.bot.inventory.items().find((stack) => stack.name === food);
    if (item === undefined) {
      return "no food";
    }
    await this.bot.equip(item, "hand");
    acted();
    await this.bot.consume();
    return `ate ${item.name}`;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
