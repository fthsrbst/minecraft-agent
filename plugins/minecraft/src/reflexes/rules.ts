/**
 * L0 reflex rules (AGENTS.md decision 10: emergencies are plain code, no model). A pure function of
 * the bot's state, so the rules are tested without a server and stay fast enough to run on every
 * relevant game event.
 */

export interface Threat {
  readonly id: number;
  readonly name: string;
  readonly distance: number;
}

export interface ReflexState {
  readonly health: number; // 0–20
  readonly food: number; // 0–20
  readonly oxygen: number; // 0–20; drops only under water
  readonly threats: readonly Threat[]; // hostile mobs nearby, any order
  readonly hasWeapon: boolean;
  readonly hasFood: boolean;
  // A skill or an action is running: eating can wait unless hunger is critical.
  readonly working: boolean;
}

export type ReflexChoice =
  | { readonly kind: "flee"; readonly target: Threat; readonly reason: string }
  | { readonly kind: "fight"; readonly target: Threat; readonly reason: string }
  | { readonly kind: "eat"; readonly reason: string }
  | { readonly kind: "surface"; readonly reason: string };

// Mobs that attack only when provoked: walking past them is safe, attacking them is not.
export const NEUTRAL: ReadonlySet<string> = new Set(["enderman", "piglin", "zombified_piglin"]);
// Fighting these in survival without gear loses: explosions, heavy damage, flying or ranged packs.
export const ALWAYS_FLEE: ReadonlySet<string> = new Set([
  "creeper",
  "warden",
  "ravager",
  "evoker",
  "vex",
  "wither",
  "elder_guardian",
  "breeze",
]);

export const DANGER_RADIUS = 8;
// A creeper's fuse starts at 3 blocks; react earlier.
export const CREEPER_RADIUS = 10;
const LOW_HEALTH = 8;
const PACK_SIZE = 3;
const HUNGRY = 14;
const STARVING = 6;
// Air runs out 15 s after it starts dropping; at 8 there is time to swim up from a few blocks deep.
const LOW_OXYGEN = 8;

function inRange(threat: Threat): boolean {
  if (NEUTRAL.has(threat.name)) {
    return false;
  }
  return threat.distance <= (threat.name === "creeper" ? CREEPER_RADIUS : DANGER_RADIUS);
}

export function chooseReflex(state: ReflexState): ReflexChoice | null {
  // Drowning first: no fight or flight works while the air runs out.
  if (state.oxygen <= LOW_OXYGEN) {
    return { kind: "surface", reason: `air ${String(state.oxygen)} is low` };
  }
  const threats = state.threats.filter(inRange).sort((a, b) => a.distance - b.distance);
  const nearest = threats[0];
  if (nearest !== undefined) {
    if (ALWAYS_FLEE.has(nearest.name)) {
      return { kind: "flee", target: nearest, reason: `${nearest.name} is too dangerous to fight` };
    }
    if (state.health < LOW_HEALTH) {
      return { kind: "flee", target: nearest, reason: `health ${String(state.health)} is low` };
    }
    if (threats.length >= PACK_SIZE) {
      return {
        kind: "flee",
        target: nearest,
        reason: `${String(threats.length)} hostiles at once`,
      };
    }
    // Measured live: bare hands do 1 damage and knockback keeps pushing the mob out of reach,
    // so an unarmed fight with a zombie (20 health) takes longer than fleeing does.
    if (!state.hasWeapon) {
      return { kind: "flee", target: nearest, reason: "no weapon" };
    }
    return { kind: "fight", target: nearest, reason: `${nearest.name} within reach` };
  }
  if (state.hasFood && (state.food <= STARVING || (state.food <= HUNGRY && !state.working))) {
    return { kind: "eat", reason: `food ${String(state.food)}` };
  }
  return null;
}
