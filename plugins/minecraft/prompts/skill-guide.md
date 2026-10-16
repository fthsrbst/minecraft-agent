Minecraft Java 1.21.11 facts for writing skills:

- Logs come in kinds (oak_log, birch_log, spruce_log, dark_oak_log, …). Each log crafts into 4 planks of the
  same kind (oak_log → oak_planks). Use whichever log kind is nearby; read `nearbyBlocks` from `bot.observe()`.
- Recipes in the 2×2 inventory grid need no table: planks, sticks (2 planks → 4 sticks), crafting_table
  (4 planks). Everything else (tools, chests, furnaces) needs a crafting_table placed within reach: craft one,
  `bot.place("crafting_table")`, then craft.
- Wooden tools need planks + 2 sticks (pickaxe: 3 planks). Stone tools need 3 cobblestone (pickaxe) + 2 sticks.
- Mining stone needs a pickaxe and drops cobblestone; mining it by hand drops nothing. Logs, dirt and sand can be
  mined by hand. `bot.collect` and `bot.dig` pick the best tool in the inventory automatically.
- Stone is usually under 1–5 blocks of dirt/grass, or exposed on hills and in cliffs. If no stone is in sight,
  dig down next to yourself with `bot.dig(x, y - 1, z)` at your own feet position, repeatedly, then look again.
- Only what is in sight counts (fair mode): `observe` and `collect` see blocks touching open air near you.
- Counts in `craft(item, count)` are items wanted, not crafts; craft enough planks first for everything after.
