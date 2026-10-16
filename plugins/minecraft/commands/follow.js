// Command skill: #follow [player] [seconds]. Stays within 3 blocks of the player while in sight.
const deadline = Math.min(args.seconds ?? 120, 600);
let lost = 0;
for (let second = 0; second < deadline; second++) {
  const observation = await bot.observe({ radius: 32 });
  const player = observation.nearbyEntities.find((entity) => entity.username === args.player);
  if (!player) {
    lost += 1;
    if (lost >= 10) {
      throw new Error(`lost sight of ${args.player}`);
    }
  } else {
    lost = 0;
    if (player.distance > 3) {
      try {
        await bot.goTo(player.position.x, player.position.y, player.position.z, { range: 2, timeoutMs: 5000 });
      } catch (error) {
        log("cannot reach", args.player, String(error));
      }
    }
  }
  await bot.wait(500);
}
return { followed: args.player };
