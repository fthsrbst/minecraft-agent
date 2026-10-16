// Hand-written skill (P2.3): collect `args.count` logs (default 3) of the nearest log type.
// Runs in the skill executor: only `bot`, `args` and `log` exist here.
const count = args.count ?? 3;
const observation = await bot.observe({ radius: 32 });
const nearest = observation.nearbyBlocks.find((block) => block.name.endsWith("_log"));
if (!nearest) {
  throw new Error("no logs within 32 blocks");
}
log(`collecting ${count} ${nearest.name}; nearest is ${nearest.distance} blocks away`);
const result = await bot.collect(nearest.name, count);
log("gained", result.gained);
return result;
