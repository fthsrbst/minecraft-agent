// Hand-written skill (P2.3): make a wooden pickaxe from nothing. The reference solution for the
// P2.4 task "craft a wooden pickaxe", and a check that craft and place work.
const observation = await bot.observe({ radius: 32 });
const logType = observation.nearbyBlocks.find((block) => block.name.endsWith("_log"));
if (!logType) {
  throw new Error("no logs within 32 blocks");
}
const plankType = logType.name.replace(/_log$/, "_planks");
// 3 logs → 12 planks: 4 for the table, 3 for the pickaxe head, 2 for sticks, 3 spare.
// collect may mine fewer than asked (unreachable blocks are skipped), so top up.
let logs = 0;
for (let attempt = 0; attempt < 3 && logs < 3; attempt++) {
  logs += (await bot.collect(logType.name, 3 - logs)).mined;
}
await bot.craft(plankType, 12);
await bot.craft("crafting_table", 1);
await bot.place("crafting_table");
await bot.craft("stick", 4);
const made = await bot.craft("wooden_pickaxe", 1);
log("crafted", made.gained);
return made;
