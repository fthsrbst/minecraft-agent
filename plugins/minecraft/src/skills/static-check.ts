/**
 * A fast first filter on skill source. It is NOT the security boundary (string checks are easy to
 * evade); the boundary is the executor process: no bot handle, no environment, Node's permission
 * model, a memory cap and a hard timeout. This check exists to give the LLM an early, specific
 * error for code that could never be allowed, before a process is started.
 */
const FORBIDDEN: readonly { readonly pattern: RegExp; readonly reason: string }[] = [
  { pattern: /\brequire\s*\(/, reason: "`require` is not available; use the `bot` API only" },
  { pattern: /\bimport\s*\(|^\s*import\s/m, reason: "imports are not available" },
  { pattern: /\bprocess\b/, reason: "`process` is not available" },
  { pattern: /\bglobalThis\b/, reason: "`globalThis` is not available" },
  { pattern: /\beval\s*\(/, reason: "`eval` is not allowed" },
  { pattern: /\bFunction\s*\(/, reason: "`Function(...)` is not allowed" },
  { pattern: /\bconstructor\b|__proto__/, reason: "prototype access is not allowed" },
  { pattern: /chat\s*\(\s*["'`]\s*\//, reason: "chat commands starting with `/` are not allowed" },
];

export const MAX_SOURCE_LENGTH = 50_000;

export function checkSkillSource(code: string): string[] {
  const problems: string[] = [];
  if (code.trim() === "") {
    problems.push("the skill code is empty");
  }
  if (code.length > MAX_SOURCE_LENGTH) {
    problems.push(`the skill code is longer than ${String(MAX_SOURCE_LENGTH)} characters`);
  }
  for (const { pattern, reason } of FORBIDDEN) {
    if (pattern.test(code)) {
      problems.push(reason);
    }
  }
  return problems;
}
