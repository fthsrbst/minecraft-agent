# Notes

A shared notebook for Fatih and the agents. Keep it short: long research goes to `research.md`, unfinished work to `backlog.md`, the schedule to `plan.md`.
Start every note with the date (YYYY-MM-DD) and the author (`Fatih` / agent name). Newest notes first.

---

## Open questions (waiting for Fatih)

- [ ] **License:** the repository is public; which license? (Suggestion: MIT, which also matches the Mindcraft parts we borrow.)

### Answered (2026-10-15, Fatih)

- [x] **Repository:** public; **everything in English**; a proper GitHub README. → AGENTS.md decision 21
- [x] **Work tracking:** a plan document instead of GitHub issues; code still via PRs that Fatih reviews. → `docs/plan.md`, AGENTS.md decision 22
- [x] **Targets:** the success thresholds in research.md §11 are accepted. → AGENTS.md decision 17b
- [x] **Multi-agent:** yes, as a future extension. → research.md §5.5, AGENTS.md decision 20
- [x] **Delivery date:** **2026-11-19** (5 weeks). → `docs/plan.md`
- [x] **Core language:** Python; the Minecraft plugin stays TypeScript. → AGENTS.md decision 1
- [x] **Second game:** Doom (ViZDoom), after delivery.
- [x] **Way of working:** Claude writes the code, Fatih reviews and learns from it.
- [x] **Review questions** (research.md §14.4, AGENTS.md decisions 5, 12, 15–19):
  - L2: Sonnet 5.5 by default, Haiku for text; cascade and Opus measured in S5.
  - Delivery scope: **everything stays** (risk managed by ordering).
  - Main claim: learning by playing.
  - "Perfect": tiered (diamond + 3 days + 25 tasks as the main target; Ender Dragon in an unknown world as stretch).
  - Visibility: two modes (fair for evaluation + full knowledge for AFK).
  - Recording: phased (v1 blueprint + macro, v2 behavioral).
  - Mindcraft: borrow parts, do not build on top.
- [x] **Autonomy:** "never ask" is an option (`full` / `approver` / `consult`, all timed). → research.md §5.6, AGENTS.md decision 9b
- [x] **Plugin architecture:** the system evolves to other games; Minecraft is a plugin. → research.md §5, AGENTS.md decision 9
- [x] **Creativity:** be creative like the GPT-6 Astra creeper story. → research.md §10
- [x] **Commands:** while AFK, natural language, voice or pipelines ("go mine / kill enemies / find this"). → research.md §9
- [x] **Skills:** must be excellent; they are the source of speed. → research.md §8
- [x] **Memory:** RAG + game history, inventory, decisions, home/portal locations, villages, found resources; never go back to an exhausted mine. → research.md §7
- [x] **GPU:** `fatih-pc` has an RTX 5070 Ti. → research.md §6.9
- [x] **Minecraft client:** Fatih installs the real game.
- [x] **Jev:** a TypeSafe API key is available; local classifiers will be tested too; game-specific synthetic data + fine-tuning is an option. → research.md §6.6–6.7
- [x] **Narration:** spoken or typed, both. → AGENTS.md decision 11b
- [x] **LLM budget:** not a constraint. → AGENTS.md decision 5b

---

## Fatih's notes

_(write here)_

---

## Agent notes

- **2026-10-15 · claude-code**: The repository was switched to English and public; the 27 Turkish GitHub issues were closed as "not planned" and replaced by `docs/plan.md` (they were not deleted; deleting is irreversible and left to Fatih).
- **2026-10-15 · claude-code**: External review (Opus 5.5 sub-agent + GPT-6-Astra via Codex) done; raw reports in `docs/reviews/`, synthesis in research.md §14. Twelve shared, high-confidence findings were applied: separate-process sandbox, emergencies in L0, action arbiter, independent predicates, train/test split and statistics, `world_instance_id`, counterfactuals only as a pilot, per-provider thresholds, thin plugin core, `approver` timeouts never grant permission, document errors.
- **2026-10-15 · claude-code**: Malde's repository is github.com/rmalde/minecraft-agent (End portal pre-verified, dragon position read by a server sensor; Jev call rate not documented). Claude's official Record-a-skill page: Mac Cowork only, ~10 minutes, video/audio not kept; the official page does not describe follow-up questions.
- **2026-10-15 · claude-code**: The claim "Unsloth is Jev-compatible, only the address changes" could not be verified (the Decision API routes `jev-latest` requests, but answers come in Laya format). An earlier note of mine said otherwise and was wrong.
- **2026-10-15 · claude-code**: Risk that the plugin contract gets shaped by Minecraft. Mitigation: a 1-day ViZDoom spike (S8) with the Doom plugin.
- **2026-10-15 · claude-code**: GPT-6 Astra correction: the sources do not mention "waited to die"; a creeper blew up the chest and bed, the model farmed potatoes for hours and became wary of green things (Vals AI, 141-hour stream). "Depression" is the media's framing.
- **2026-10-15 · claude-code**: External validation: on 2026-09-20 Ronak Malde killed the Ender Dragon in 8 min 43 s for under $1 with GPT-6 Astra (35 calls) + Jev (131 calls) + Mineflayer (peaceful, known seed/route). Similar to our L2 + L1 + L0 split; worth reading the harness in the repo before P1.4.
- **2026-10-15 · claude-code**: Vals CUA-Bench (pixels + keyboard/mouse only): no model found iron in Minecraft. Supports our state-API path.
- **2026-10-15 · claude-code**: The biggest lever for skill speed-up: a general `obtain(item, n)` recipe solver in code. It replaces the hundreds of craft/mine skills Voyager had the LLM write.
- **2026-10-15 · claude-code**: Core memory idea: "where is home" is a coordinate and "should I go to that mine" is a calculation → structured queries and utility, not vector search. RAG only for free-text history ("why did we leave the east?"). The "RAG only" ablation arm tests this claim.
- **2026-10-15 · claude-code**: Cascade warning (Signed Rescue Routing, 2026): a large model can also break a small model's correct answer → measure the net benefit of each escalation trigger.
- **2026-10-15 · claude-code**: Claude Record a skill and Codex Record & Replay both produce **interpreted instructions** (SKILL.md) and leave testing to the user. Our difference: an exact game event stream + an executable code skill + an intent card + automatic verification in fresh worlds.
- **2026-10-15 · claude-code**: Unsloth published "decision model" training (Qwen3.5 0.8B–4B, Gemma 4 E4B; probabilities + calibration). Jev compatibility not verified (see above).
- **2026-10-15 · claude-code**: No existing work turns recorded human Minecraft play into Mineflayer skills → record a skill can be this project's original contribution. `minecraft-protocol` ships a ready `examples/proxy` (v1.68).
- **2026-10-15 · claude-code**: No Java on the Mac, Docker 28.3 available → `itzg/minecraft-server` is the easiest server. LM Studio installed, no Ollama. Node 22.23, Python 3.14 (use 3.13 via uv for library compatibility).
- **2026-10-15 · claude-code**: `mineflayer@4.39.0` (2026-09-06) tested versions: 1.8.8 … 1.21.11, 26.1. Mindcraft and minecraft-mcp-server support up to 1.21.11 → 1.21.11 is the safest common point.
- **2026-10-15 · claude-code**: Ideas worth copying from Voyager's source: (1) only `[system, human]` per attempt, with "last code + error + critique" instead of history; (2) primitives implemented separately from the simplified versions shown to the LLM; (3) the curriculum deliberately avoids tasks needing visual verification; (4) peaceful → easy after 15 tasks.
- **2026-10-15 · claude-code**: Evaluation warning: 2026 skill research (SkillsBench, "skills in the wild") shows skill benefits are fragile → the library's contribution must be proven with a "no library" ablation, otherwise the main claim is empty.
