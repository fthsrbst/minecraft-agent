/**
 * Decides the hello bot's answer to one chat line. Kept free of Mineflayer so it can be unit-tested;
 * from P3.2 on, chat goes to the core's command parser instead.
 */
export function replyTo(sender: string, message: string, botName: string): string | null {
  // Ignore our own messages, or the bot would answer itself forever.
  if (sender === botName) {
    return null;
  }
  if (!message.toLowerCase().includes(botName.toLowerCase())) {
    return null;
  }
  return `Hi ${sender}! I am ${botName}, a learning agent. I heard you say: "${message.trim()}"`;
}
