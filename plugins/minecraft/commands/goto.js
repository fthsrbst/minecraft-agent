// Command skill: #goto. args.target is { x, y, z } (the core resolves place names).
const { x, y, z } = args.target;
const result = await bot.goTo(x, y, z, { range: 1 });
return { arrived: result.position };
