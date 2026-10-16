// Command skill: #mine <block> [count].
const result = await bot.collect(args.block, args.count ?? 1);
return { mined: result.mined, gained: result.gained, complete: result.complete };
