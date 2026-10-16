// Test fixture (P3.1): a skill that keeps working for `args.seconds` (default 30), observing each
// second, so a reflex has something to interrupt.
const seconds = Math.min(args.seconds ?? 30, 120);
for (let i = 0; i < seconds; i++) {
  await bot.wait(1000);
  await bot.observe({ nearby: false });
}
return { worked: seconds };
