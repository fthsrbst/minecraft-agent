# Research and Design: A Learning Game Agent (first game: Minecraft)

> Last updated: 2026-10-15. This is the single research and design document; new research is added here as sections.
> Final decisions live in the decision table in [`AGENTS.md`](../AGENTS.md). The implementation schedule lives in [`plan.md`](plan.md).

## 0. Summary and vision

**What we are building:** not just a Minecraft bot, but a **general bot system that can learn to play different games**. The system accumulates a **skill library** as it plays and as it watches a human play. The first game is Minecraft, and the prototype should play it "perfectly" (the measurable definition is in §11).

**Main ideas:**

1. **The Voyager loop** (§1): a curriculum proposes a task → an LLM writes skill code → the code runs in the game → the result is verified independently → the skill enters the library.
2. **Decision layers** (§6): plain code handles reflexes and emergencies (L0); a fast decision model such as TypeSafe **Jev** makes small, event-driven tactical choices (L1); a frontier LLM plans and writes code (L2; Claude Sonnet 5.5 by default, Haiku 5.5 for high-volume text); offline learning labels data and fine-tunes local decision models (L3). Every decision is made by the fastest layer that is good enough.
3. **Record a skill** (§4): the player teaches by playing, with spoken or text narration; the system turns the demonstration into a parameterized, automatically tested skill. Claude's and Codex's recording features were studied in detail.
4. **Game memory** (§7): a world map (home, portal, villages, mines… with location and status), resource state ("is this mine exhausted?"), chest contents, an event log and past decisions. Location and resource questions are answered by structured queries in code; RAG is used only for free-text history.
5. **Skill design** (§8): a five-level hierarchy, a contract and tests for every skill, a general `obtain(item, n)` solver and a hand-written starter library. This is where most of the speed comes from.
6. **Commands and pipelines** (§9): natural language, voice or a visual pipeline compile into one task graph (conditions, triggers, guards, budgets). Example: "while I'm AFK, mine iron, empty the inventory at home when full, sleep at night".
7. **Creativity and personality** (§10): inspired by GPT-6 Astra's "creeper incident"; recovery after a big loss, an optional persona and mood, a diary, highlight moments.
8. **Multi-agent** (§5.5): several bots in the same world sharing work is a planned future extension.

**How generality works (§5):** the core knows no game; **Minecraft is a plugin**. Each game connects through a plugin that provides a thin runtime protocol plus optional capabilities (primitives, predicates, a knowledge provider, a vocabulary, a scenario builder, a recorder…). The next plugin, after delivery, is Doom (ViZDoom).

**Autonomy (§5.6):** the autonomy level is an **option**: `full` (never asks), `approver` (asks only for risky actions), `consult` (consults). In every mode a question never blocks the bot: each question has a timeout and a default answer (the bot's own decision), and a timeout never grants extra permission. AFK work defaults to `full`.

**External review (§14):** Claude Opus 5.5 and GPT-6-Astra independently critiqued the design. Their shared findings are already applied throughout this document: isolated skill execution in a separate process, emergencies handled in L0, a single action arbiter, independent verification predicates, a strict train/test split with proper statistics, and a thin plugin core.

**A correction — did Jev "finish Doom"?** No, the available sources do not support that (§2.3):
- TypeSafe's own demo is a **speed demonstration**: it feeds the game state as text and makes about 10 decisions per second. According to coverage, a scripted bot would beat it.
- The community repo `jev-plays-doom` scored **the same** average as a hand-written aiming bot in a single arena (`defend_the_center`, 6.55 kills).
- Blocks.ai's open replica collected 5 kills and 8 items in 300 decisions on Freedoom MAP01 without dying; finishing the level is not reported.

The real lesson: "the model makes small decisions **fast**; code does the rest."

---

## 1. Minecraft agents: Voyager and its competitors

### 1.1 Two families

| Family | Observation | Action | Examples | For us |
|---|---|---|---|---|
| **Code / API based** | Text from the game API: inventory, blocks, position… | The LLM writes **code** that calls the bot API | Voyager, Mindcraft, ODYSSEY, MindForge, Project Sid | ✅ Minecraft prototype |
| **Pixels / keyboard-mouse (VLA)** | Screenshots | A trained policy emitting low-level inputs | VPT, STEVE-1, JARVIS-1, Optimus-1/2/3, Lumine, NitroGen, Game-TARS | ⚠️ Fallback path for games without an API (§3) |

Mineflayer is a Node.js bot that connects to a Minecraft server **like a real player**. It provides APIs for pathfinding (`mineflayer-pathfinder`), digging, crafting, inventory, combat (`mineflayer-pvp`), archery (`minecrafthawkeye`) and block collection (`mineflayer-collectblock`). The LLM's job is to write programs that call this API in the right order and under the right conditions.

### 1.2 Voyager: the architecture, read from the source code

Source: Wang et al. 2023 ([arXiv 2305.16291](https://arxiv.org/abs/2305.16291), NeurIPS 2023); code: [MineDojo/Voyager](https://github.com/MineDojo/Voyager) (MIT, unmaintained).

| Component | File | Role |
|---|---|---|
| CurriculumAgent | `voyager/agents/curriculum.py` | Proposes the next task ("Mine 3 iron_ore"). First asks itself questions and caches the answers in `qa_cache.json`. |
| ActionAgent | `voyager/agents/action.py` | Writes an `async function xxx(bot)` JavaScript function |
| CriticAgent | `voyager/agents/critic.py` | Produces `{reasoning, success, critique}` JSON from the final state |
| SkillManager | `voyager/agents/skill.py` | Has the LLM describe a successful program, embeds the description into Chroma, retrieves top-k=5 |
| VoyagerEnv | `voyager/env/bridge.py` + `env/mineflayer/index.js` | Python ↔ Node Express bridge (`/start`, `/step`). Code runs through a bare `eval`. |

**Loop:** at most 160 iterations in total and at most 4 attempts per task. Each attempt sends only two messages, `[system, human]`: instead of history, "last code + error + critique" is embedded in the human message, which keeps the message count fixed (the message content can still grow). After 15 completed tasks the world switches from peaceful to easy.

**Other notable details:**
- After a failed building attempt it collects the placed blocks back (`reset_placed_if_failed`).
- It keeps chest contents in memory.

**Observation:** last code, error, chat log, biome, time, nearby blocks, nearby entities, health, hunger, position, equipment, inventory (xx/36), chests, task, context, critique.

**Primitives:** `mineBlock`, `craftItem`, `smeltItem`, `placeItem`, `killMob`, `exploreUntil`, `useChest`, `shoot`, `waitForMobRemoved`. The real implementation (`control_primitives/`) and the simplified version shown to the LLM (`control_primitives_context/`) live in separate files, which is a good idea.

**Prompt rules (`prompts/action_template.txt`):**
- Use the primitives; do not make raw calls like `bot.dig`.
- Write generic, reusable code; do not trust the inventory, collect what is missing first.
- No infinite loops or recursion; do not register event listeners with `bot.on`.
- `maxDistance` for `findBlocks` is always 32 ("Do not cheat").
- Response format: `Explain → Plan → Code`.

**Curriculum rule:** tasks that need visual verification (building, placing, planting, trading) are not proposed.

**Results:**
- 3.3× more unique items than the previous state of the art.
- Tech-tree milestones reached up to 15.3× faster.
- In ablations, the curriculum, the skill library and self-verification were all critical.

**Weaknesses:**
- GPT-4 cost: "thousands of dollars" per experiment according to the ODYSSEY authors.
- It can propose impossible tasks ("copper sword").
- It can invent functions that are not in the primitive list.
- It runs code with an unsandboxed `eval`.
- Success is judged entirely by an LLM.
- It does not learn lasting lessons from failure.
- **No real-time reaction**: it cannot react to danger while code is running; experiments are mostly in peaceful mode.
- Pinned to MC 1.19 and Azure login.

### 1.3 Competitors (code / API based)

| System | Key idea | Lesson |
|---|---|---|
| **Mindcraft** + MineCollab ([repo](https://github.com/mindcraft-bots/mindcraft), [arXiv 2504.17950](https://arxiv.org/abs/2504.17950)) | Pure Node, ~47 parameterized commands (`!collectBlocks("oak_log",1)`) plus an optional code mode. Many providers, multi-agent. ~5.9k⭐, active, MC ≤1.21.11, MIT. | The most mature open-source project. The "commands or code" trade-off. Performance drops by as much as 15% when agents must communicate detailed plans. We borrow parts of it (§5.4). |
| **ODYSSEY** ([arXiv 2407.15325](https://arxiv.org/abs/2407.15325)) | 40 primitive + 183 compositional ready-made skills; LLaMA-3 fine-tuned on the wiki; planner–actor–critic. | Give the agent a strong **starter library**; cheap open models become usable. |
| **MindForge** ([arXiv 2411.12977](https://arxiv.org/abs/2411.12977)) | Voyager + theory of mind + communication between agents | Open 7–8B models struggle even with basic tasks inside Voyager. |
| **MineEvolve** ([arXiv 2603.13131](https://arxiv.org/abs/2603.13131), 2026) | Typed feedback (inventory delta, failure type, stagnation). Extracts skills from successes and **remedies** from failures. | Learning from failure. |
| **Evolving Programmatic Skill Networks** ([arXiv 2601.03509](https://arxiv.org/abs/2601.03509), 2026) | Skills form a network of programs that call each other; fault localization, maturity-gated updates, refactoring validated by rollback. | As a library grows it needs **repair and simplification**. |
| **Project Sid / PIANO** ([arXiv 2411.00114](https://arxiv.org/abs/2411.00114)) | 1000+ agents; concurrent modules (memory, action, social, speech) and a decision bottleneck | **Parallel modular** architecture for real-time behavior; reference for the multi-agent extension. |
| **GITM** ([arXiv 2305.17144](https://arxiv.org/abs/2305.17144)) | Goal → subgoal → structured action; no GPU | Hierarchical decomposition. 67.5% on ObtainDiamond. |
| **minecraft-mcp-server** ([repo](https://github.com/yuniko-software/minecraft-mcp-server)) | Exposes Mineflayer to Claude as MCP tools | No learning, but a reference for an interactive demo. |
| **Player2NPC / PlayerEngine** ([Modrinth](https://modrinth.com/mod/player2npc)) | Commercial "AI companion" Fabric mod: the LLM emits commands, an engine executes them | Product counterpart; no learning. |

Pixel-based Minecraft agents:
- **JARVIS-1** ([arXiv 2311.05997](https://arxiv.org/abs/2311.05997)): multimodal memory, 12.5% on ObtainDiamondPickaxe.
- **Optimus-1** ([arXiv 2408.03615](https://arxiv.org/abs/2408.03615)): knowledge graph + experience pool.
- **VPT**, **STEVE-1**.

### 1.4 Benchmarks

- **MCU**: long-horizon tasks.
- **MineCollab**: task JSON format (`goal`, `initial_inventory`, `target`, `timeout`, `blocked_actions`) → **template for our test set**.
- **MineNPC-Task** ([arXiv 2601.05215](https://arxiv.org/abs/2601.05215)): machine-checkable validators, out-of-world shortcuts forbidden. GPT-4o's recurring failures were in code execution, inventory handling, references and navigation.
- **MineExplorer** ([arXiv 2605.30931](https://arxiv.org/abs/2605.30931), EMNLP 2026): sharp drops as hidden prerequisites grow longer; bigger models or thinking modes do not help consistently.
- **PillagerBench** ([arXiv 2509.06235](https://arxiv.org/abs/2509.06235)): competitive team play.

### 1.5 Lessons from skill-library research (2026)

- **Skill drift** ([arXiv 2605.10990](https://arxiv.org/abs/2605.10990)): skills **break silently** when the APIs or versions they depend on change. Extract an "environment contract" from each skill and check it proactively.
- **SkillsBench** ([arXiv 2602.12670](https://arxiv.org/abs/2602.12670)) and "Skills in the wild" ([arXiv 2604.04323](https://arxiv.org/abs/2604.04323)): the benefit of skills is fragile. The library's contribution must be proven with **ablations**.

---

## 2. Jev and System One models

### 2.1 What is Jev?

**Jev** is TypeSafe AI's first "System One" model. The CEO is Diogo Almeida (former OpenAI researcher, co-inventor of RLHF); the company has raised $40M ([The Register](https://www.theregister.com/ai-and-ml/2026/09/16/typesafe-ai-debuts-model-for-machines-that-plays-doom/5296711)).

**It does not generate text.** It takes program state (JSON or text) and returns **typed, probabilistic decisions**. All questions are answered in one parallel pass.

| Primitive | Returns | Game example |
|---|---|---|
| **Choice** | One of the defined options + a probability per option + confidence | "What now: fight / flee / eat / continue" |
| **Noul** | Probability of "yes" | "Is a mob close enough to hurt me within a second?" |
| **Score** | Position on defined levels | "How hard is this task with the current inventory?" |
| **Box** (Jev 1.14, experimental) | A bounding box in an image | Finding an enemy or a button on screen |

**Numbers:**
- **Latency:** 70–500 ms (company claim, "40–200× faster than LLMs"). Community measurement: 212 ms average over 2,642 calls in Doom.
- **Price:** $0.042 per 1M input tokens, output free ([models](https://docs.typesafe.ai/models.md)).
- **Context:** 64k tokens per request, 32k per question (262k with a special header; slower and less accurate).
- **Versions:** `jev-1.13.0` stable, `jev-1.14.0` preview since 2026-10-14.
- **Images:** PNG/JPEG, 256–1568 px per side, with the `TypeSafe-Danger-Zone-Images: true` header; labeled "not production-ready" ([images](https://docs.typesafe.ai/images.md)).
- **Access:** hosted API only, early access, no downloadable weights. JS and Python SDKs.

### 2.2 Weaknesses (official "jaggedness" page, [jev-1.13](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md))

- **Not a calculator:** counting, arithmetic and precise numeric comparison are unreliable → **code must compute distances, angles and counts**.
- **Long, irrelevant state** lowers accuracy (context rot) → give the model only the relevant fields.
- **Option order** can change the answer (bias toward the first option) → shuffle and test consistency.
- Literal reading, multi-hop indirection and adversarial content inside the state are also weak points.
- Typed output guarantees the **interface**, not **correctness**. Accuracy must be measured per use case.

### 2.3 The Doom experiments: what actually happened

| Experiment | Setup | Result |
|---|---|---|
| TypeSafe official demo | Structured state (health, enemy positions, distances), ~10 decisions per second, ~$7/hour ([LumaDock](https://lumadock.com/blog/what-is-jev-typesafe), [Medium](https://medium.com/@creativeaininja/typesafes-jev-makes-ai-decisions-fast-enough-to-play-doom-68fdcce1159a)) | A speed demo. A scripted bot would beat it; it makes a real-time loop possible where 3–30 s LLM calls cannot. |
| [jev-plays-doom](https://github.com/tirukovelamanoj/jev-plays-doom) | ViZDoom; `describe()` computes enemy angle and distance **in code**. Two questions per request: `action` (Choice: ATTACK/TURN_LEFT/TURN_RIGHT) and `in_danger` (Noul). One decision every 4 ticks (~8.75 Hz). Below 0.5 confidence it hands over to a hand-written brain. | `defend_the_center`, 20 episodes: random 0.75, hand-written aim 6.55, Jev 6.55 kills. **Prompt wording is critical**: "rule" criteria 6.20, "intent" criteria −0.60 (never fired, kept turning). Episode variance (4–5 kills) is larger than many of the measured differences. |
| [Blocks.ai open replica](https://blocks.ai/blog/jev-open-model-doom) | Gemma 4 12B **base** model. One forward pass, softmax over the logits of letters A–Z → cannot invent a label. Prefix KV cache. Median 113 ms on an M4 Mac. | Three scenarios + Freedoom MAP01: 5 kills, 8 items, no deaths in 300 decisions. **Navigation was moved to BFS code**: when the model picked a direction every tick it oscillated; with BFS, stuck decisions fell from ~33 to 3. Engine data selects the phase (combat / stuck / navigate); the model only chooses the local direction. |

### 2.4 Takeaways for us

1. **Fast layers are needed**: (a) **reflex code**, ~0 ms: pathfinding, aiming, distances, and emergency reactions; (b) **System 1 / Jev**, ~100–300 ms: small, contextual, event-driven decisions; (c) **System 2 / LLM**, seconds: planning, code, curriculum, turning recordings into skills.
2. Jev's place in Minecraft is **not writing skills** and **not emergency reflexes**. It is contextual choice while skills run:
   - **Tactical choice after the L0 reflex:** continue / retreat / fight / eat / shelter, event-driven.
   - **Skill selection and reranking:** TypeSafe's [skill suggestion](https://docs.typesafe.ai/cookbooks/skill_suggestion.md) recipe cut wrong skill loads from 16.8% to 7.3% over 182 skills (two calls, under 1 s in total). Embedding prefilter + Jev rerank.
   - **Language-semantic decisions:** player command → skill, narration sentence type, stagnation detection.
   - **Fuzzy verification** (Noul) where deterministic checks are not enough, before an LLM critic.
   - **Confidence-gated routing:** below threshold, fall back to a rule or to the LLM.
3. **Cost estimate:** even at 2k tokens of state × 5 Hz × 3600 s ≈ 36M tokens/hour ≈ **$1.5/hour**; event-driven use is far cheaper. TypeSafe's Doom demo was ~$7/hour.
4. **Dependency risk:** Jev is a closed service. It sits behind the `DecisionClient` interface and local decision models are compared through the same interface (§6.5–6.7).

### 2.5 Jev + GPT-6 Astra + Mineflayer: Ender Dragon in 8 min 43 s (2026-09-20)

Ronak Malde's experiment ([ASCII.jp](https://ascii.jp/en/elem/000/004/436/4436545/), repo [rmalde/minecraft-agent](https://github.com/rmalde/minecraft-agent), "Astra planner and JEV controller"):
- **Division of labor:** GPT-6 Astra makes the high-level plan (what to achieve now, where to go). Jev takes position + inventory + surroundings + Astra's goal and picks one of the candidate actions (travel, mine, collect, craft, attack). Mineflayer executes.
- **Parallelism:** Astra plans in the background while Jev keeps choosing; the game never pauses.
- **Numbers:** 35 Astra calls (~$0.96), 131 Jev calls (~$0.01). The call rate is not documented (131 decisions / 523 s ≈ 0.25 Hz).
- **Setup:** MC 1.16.5 (vanilla server), peaceful, fixed seed; the End portal at a pre-verified coordinate; a village and 3 chests with 21 obsidian in the seed; route through the Nether, no blaze rods needed; dragon killed with bed explosions. The dragon head position is read by a read-only **sensor** added to the server (`DragonObserver.java`). One verified run.
- **What it means for us:** it shows that the **integration** of an L2 planner, an L1 candidate-action chooser and an L0 executor can work. It does **not** show learning or the causal contribution of L1, and L1 ran at ~0.25 Hz, event-driven. Our differences: an unknown world, real difficulty, and learning.

---

## 3. General game-playing agents (toward "any game")

| System | Input → output | Key result | For us |
|---|---|---|---|
| **SIMA 2** (DeepMind, [arXiv 2512.04797](https://arxiv.org/abs/2512.04797), 2025-11) | Pixels + language → keyboard/mouse; Gemini-based | Approaches humans in many 3D games. Overall task completion SIMA 1 31% → SIMA 2 65% (not Minecraft-specific; much lower in new games). In new environments it **generates its own tasks** and improves with a reward model. | Self-curriculum + reward model idea; scale far beyond our scope. |
| **Cradle** (BAAI, [arXiv 2403.03186](https://arxiv.org/abs/2403.03186)) | Screenshots → keyboard/mouse **code**; no API | Completed 40-minute main missions in RDR2; also Stardew Valley, Cities: Skylines, Chrome… | **Closest general architecture**: 6 modules (information gathering, self-reflection, task inference, **skill curation**, action planning, memory). Template for the "no API" path. |
| **Lumine** (ByteDance Seed, [arXiv 2511.08892](https://arxiv.org/abs/2511.08892)) | VLM, a few fps → high-frequency keyboard/mouse; thinks only when needed | Finished Genshin Impact's 5-hour main story at human speed; transferred without training to Wuthering Waves and Honkai: Star Rail. | "Think only when needed" = our layer split. Training cost not suitable for us. |
| **NitroGen** (NVIDIA, [arXiv 2601.02427](https://arxiv.org/abs/2601.02427), CVPR 2026) | RGB → gamepad; 40k hours of video from 1000+ games, actions extracted from video automatically | Up to 52% relative improvement over training from scratch in new games. **Open weights**, inference server for Windows games. | Candidate **reflex policy** for gamepad games (weak in RTS/MOBA). |
| **Game-TARS** (ByteDance, [arXiv 2510.23691](https://arxiv.org/abs/2510.23691)) | One human-like keyboard/mouse action space; 500B tokens of pretraining | ~2× the previous SOTA in open-world Minecraft; beats GPT-5/Claude-4 in FPS (authors' claim). | Unified action space idea. |
| **SpeedrunBench** (Patronus, [arXiv 2610.08076](https://arxiv.org/abs/2610.08076), 2026-10) | Screenshots (online) or editing action traces (offline); 9 games | In Pokémon Blue only three models reached the first badge (Claude Opus 5 ~160K frames; human record ~40K). No model reached a world record. | Frontier LLMs are still slow at real-time play from pixels → **games with a state API first**. |
| **Vals AI CUA-Bench** (2026-09-18, [summary](https://hermes-ai.net/news/vals-ai-s-cua-bench-humbles-every-frontier-agent-below-20-points/)) | Screen + keyboard/mouse only; 6 games, 3 hours per game | No model scored above 20/100; **no model found iron in Minecraft**; models act every 15–59 s. | Confirms the state-API + code-skills path (level A). |
| Other benchmarks | lmgame-Bench (ICLR 2026), VideoGameBench, BALROG, PokeGym, Orak | — | References for later plugins. |

**Three integration levels:**

| Level | How we connect | Examples | Agent strength |
|---|---|---|---|
| **A: state API** | The game's API / a bot library / RAM reading | Minecraft (Mineflayer), Doom (ViZDoom), Game Boy/NES (PyBoy, stable-retro), Factorio (mod API), browser games (DOM) | Highest: exact state, exact verification, code skills |
| **B: mod / hook** | A mod, plugin or memory reader | Stardew (SMAPI), Unity games (BepInEx) | High, but game-specific work |
| **C: pixels + input only** | Screenshots + keyboard/mouse/gamepad | Any game (the Cradle/Lumine path) | Lowest; perception via VLM or Jev images/Box, NitroGen as a reflex policy |

**Strategy:** the core is designed to support all three levels, but it **perfects level A first** (Minecraft). The next plugin is also level A (Doom). Level C comes later.

---

## 4. Record a skill: learning from demonstration

Goal: **the player can teach the bot by playing.** Narration can be **spoken or typed**.

### 4.1 Claude "Record a skill" (Anthropic, Cowork): detailed review

Official source: [Claude help center](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills). Other rows come from press and hands-on guides.

| Topic | What is known |
|---|---|
| Release | 2026-07-21, Claude Desktop → **Cowork**. Pro / Max / Team plans. **Cowork on Mac only** (official); not in chat, Windows, Free or Enterprise. |
| Starting | In Cowork: **"+" → Record a skill**, or **Customize → Skills → Add → Record your screen**. Screen recording and accessibility permissions are requested the first time. Pick a microphone → **Start recording** → narrate while working → **Done**. |
| What is captured | Screen activity, clicks, typing, **voice narration**. **Everything** visible on screen and everything said is captured. |
| Retention | Video and audio are **not kept** after Claude reviews the recording; a set of screenshots is kept in the task's "Recorded demonstration" step and deleted with the task (official). |
| Time limit | About **10 minutes** per recording, with a countdown in the last minute; at zero the recording stops and is sent to Claude (official). |
| After recording | 1) According to a hands-on guide, Claude asks **follow-up questions** about gaps in the narration (e.g. "where should results go?"); **the official page does not describe this**. 2) A **new skill** proposal shows *Save / Dismiss*; an **update to an existing skill** shows *Update / Dismiss*. 3) Expanding **Content** shows activation conditions, priorities, exclusions and output structure. |
| Output | A Skill in the library (folder + `SKILL.md`). The internal format is not published; user reports describe activation conditions, priorities, exclusions and output structure. |
| Replay | The skill is loaded when a matching request comes in, or runs as a scheduled task. The model executes it by **interpretation** (not coordinate replay). |
| Recommended use | One workflow per skill. **Narrate exclusions and the reasons for them.** Read the Content before saving. Test on new inputs. Never record passwords or confidential data. |

**Observed problems** ([remio](https://www.remio.ai/post/claude-cowork-skill-recording-turns-demonstrations-into-reusable-workflows-but-t), [leadwithai](https://www.leadwithai.co/article/record-a-skill-claude-cowork)):
- **Over-generalizing from one example**: incidental details can be mistaken for rules.
- **Mistakes in the demo are learned too**: a recorded skill can reproduce hidden mistakes as efficiently as good judgment.
- How unrelated speech is separated from narration is not explained.
- Experts apply rules without saying them (tacit knowledge).
- The same click can hide different intents.
- Interpreted execution is flexible but unpredictable.
- UI changes break skills.
- When something goes wrong it is hard to tell whether the demo, the interpretation or the model is at fault.
- Main lesson: **recording makes skills easier to create but harder to verify.**

### 4.2 OpenAI Codex / ChatGPT "Record & Replay": detailed review

Source: [official docs](https://learn.chatgpt.com/docs/extend/record-and-replay) + hands-on reports.

| Topic | What is known |
|---|---|
| Release | June 2026 (June 18 according to secondary sources). **macOS only.** Computer Use must be enabled. EU, UK and Switzerland excluded at first (secondary). If an organization sets `[features].computer_use = false` in `requirements.toml`, it is disabled too. |
| Starting | ChatGPT (Work mode) or Codex → **Plugins** → **"+" → Record a skill** → review the suggested prompt, **add context** → approve recording → perform the workflow → stop from the menu bar or overlay, or tell the chat you are done. |
| What is captured | "The **actions and window content** needed to learn the workflow." Runs until stopped. Audio and keystroke capture are not documented. One source claims a 30-minute cap (unverified). |
| Output | `SKILL.md` (+ optional supporting files), by default in `~/.codex/skills/<name>`. Content: **when to use it, which inputs it needs, which steps to follow, how to verify the result.** Can be refined through chat afterwards. |
| Example ([azukiazusa](https://azukiazusa.dev/en/blog/workflow-to-reusable-skill/)) | Sections of a time-entry skill: *Collect Inputs* (ask only for missing/ambiguous values) → *Open app* (browser automation if available, otherwise Computer Use) → *Enter Rows* (a 7-step per-row procedure) → *Verify* (check saved rows and totals) → *Safety* (do not touch unrelated records). **Recorded values are treated as examples, not defaults**; targets are described by **accessible labels and roles**, not coordinates; if verification fails it **stops** instead of retrying (avoids duplicate entries). |
| Replay | In a new chat, ask for the skill and provide the values that differ this time. Executed with the available tools (Computer Use, browser, plugins). |
| Official tips | Keep the demo short and complete. **State the goal and the inputs that may vary before recording.** Use realistic but non-sensitive data. Afterwards, add **hidden preferences** (naming conventions, defaults, decision points). Stop when done; do not record unrelated cleanup. |

**Audit checklist** ([chatgptaihub](https://chatgptaihub.com/audit-repair-codex-record-replay-skill)). Ten common failure modes of demonstrated skills:
1. A recorded value reused instead of an input.
2. Hidden preferences.
3. Overbroad scope.
4. UI drift.
5. Incidental (unneeded) actions.
6. On-screen text treated as an instruction.
7. Unverified success.
8. Environment and permission gaps.
9. A pre-existing result mistaken for the new one.
10. Missing stop conditions.

Suggested remedy: classify every value as **required input / fixed boundary / recorded observation / unresolved assumption**.

### 4.3 Comparison and lessons for us

| | Claude Record a skill | Codex Record & Replay | **Our game version** |
|---|---|---|---|
| Input | Screen + clicks + keys + **voice** | Actions + window content | **Game events (exact)** + state snapshots + **spoken or typed narration** |
| Before recording | — | Goal + variable inputs are asked | `consult`: may ask (with timeout); `full`: never asks, the bot infers from the recording |
| After recording | **Follow-up questions**, Save/Update/Dismiss | Refinement through chat | Depends on autonomy (§5.6): `consult` asks follow-ups with a timeout and proposes; `full` asks nothing, reports its assumptions and decides Save/Update/Discard from the verification score |
| Output | SKILL.md (interpreted instructions) | SKILL.md (when / inputs / steps / verification) | **Two artifacts**: (1) an executable **code skill**, (2) an **intent card** (when to use, inputs, rules, stop conditions, completion predicate) |
| Execution | The LLM interprets (flexible, unpredictable) | LLM + Computer Use interpret | **Code runs deterministically**, L1 watches, L2 repairs from the intent card if it breaks |
| Verification | The user tests manually | The user supervises the first replays | **Automatic**: replay in fresh worlds with varied parameters, measured by the success predicate |
| Generalization | One example | One example | **1–3 demonstrations**; differences between them become parameters |

**What we adopt** (adapted to the autonomy level, §5.6):
1. **Narration carries the reasoning.** Actions alone are not enough; "why" and "when not to" sentences become rules in the skill.
2. **Optional intent statement:** the player may say what they are teaching and which values may vary; otherwise the bot infers it.
3. **Filling gaps without asking (in `full`):** instead of follow-up questions, the bot fills gaps from memory, similar skills and recording evidence, writes its assumptions into the intent card and reports them.
4. **Recorded values are examples, not defaults.**
5. **Describe targets semantically:** "the nearest oak tree", not coordinates.
6. **If verification fails, stop; do not retry blindly.**
7. **New skill or update of an existing one** (the bot decides).
8. **Value classification** (from the Codex audit checklist).

**What neither product has, and we add:**
- **An exact event stream.** In a game we get exact events from the protocol instead of guessing from pixels, which removes the weakest link (perception) of both products.
- **An automatic test-and-repair loop**: an acceptance/repair gate before saving, which Work2Skill's induction pipeline also lacks.
- **Cleaning mistakes and detours.** Narration such as "oops, ignore that" and detours in the demo are flagged by L1 and removed automatically; the decisions are written to the decision log.
- **Blueprints for structures.** A building demo becomes a voxel plan relative to an anchor. The skill becomes "build this plan at the chosen spot".

### 4.4 Research

- **Work2Skill** ([arXiv 2610.12984](https://arxiv.org/abs/2610.12984), 2026-10):
  - **Recording:** WorkRecorder aligns screen video, keyframes, mouse/keyboard and the accessibility tree on one timeline.
  - **Skill induction:** an agent inspects evidence on demand and writes SKILL.md with workflow rules, step dependencies, selection rules, stop conditions and completion checks; values become parameters.
  - **Result:** +3–7.5 points on OSWorld, +4.7–10.5 on MyPCBench.
  - **Ablation:** removing images, UI annotations or key logs costs 5–11 points.
  - **Gap:** the paper evaluates skills downstream, with jitter and model transfer, but the induction pipeline has **no automatic verification/repair gate before saving**.
- **Hierarchical demonstrations** ([arXiv 2606.20978](https://arxiv.org/abs/2606.20978)):
  - **Named subgoal groups** instead of a flat log raise success on vague tasks from 76.7% to 90.7%.
  - Pre/postcondition and parameter annotations showed no measurable benefit.
- **ALLOY** (demonstration → graph workflow), **AWM** (workflows from traces), **Skill-Pro** (ICML 2026; activation + execution + termination conditions).
- **VPT / NitroGen**: recovering actions from unlabeled video (inverse dynamics), for recording in level-C games.
- We found **no existing work** that records human Minecraft play and turns it into bot skills → an original contribution.

### 4.5 Recording in Minecraft

| Method | Captures | Pros | Cons |
|---|---|---|---|
| **Recording proxy** (the ready `examples/proxy` of `minecraft-protocol`, v1.68) | **All packets** between the human client and the server: digging, placing, window clicks (crafting), held item, movement, inventory/block updates, **chat messages** | Vanilla server + vanilla client, no mods. Exact. Typed narration comes for free (timestamped chat packets). | Needs a packet → event translator. 1.20.2+ configuration phase, signed chat (`enforce-secure-profile=false`), and two crafting paths (recipe book packet and slot clicks) must be handled. |
| Server plugin (Paper) | Ready-made semantic events | Easy events | Java plugin, Paper server |
| Watcher bot | World changes only | Simple | Inventory and crafting are invisible |
| Screen recording | Video + input | Works in any game | Unnecessary loss in Minecraft |

**Choice: the recording proxy.** The player connects their own Minecraft client to the proxy at `localhost:25566`; the proxy forwards to the real server.

**Narration channels (both supported):**
- **Text:** in-game chat notes such as `// build the table first, go into the shelter if it gets dark`. The proxy already captures chat; the `//` prefix separates narration from normal chat.
- **Voice:** microphone → local **Whisper** (on `fatih-pc` or `mlx-whisper` on Mac), aligned to the event timeline with word-level timestamps. Optional push-to-talk records only narration moments.

### 4.6 From recording to skill (game-independent pipeline)

```
0. INTENT       the player may state the goal + variables; in consult mode the bot may ask (with timeout); full never asks
1. RECORD       plugin event stream + state snapshots + narration (speech→text or // chat)
2. ABSTRACT     raw → semantic events ("broke oak_log ×3", "crafted planks ×4", "placed crafting_table")
                positions → relative to an anchor (player start, placed table, target tree)
                keep four layers apart: client request / server ack / observed change / inferred meaning
3. CLEAN        L1: each narration sentence → {instruction, rule/exclusion, correction ("ignore that"), chatter}
                L1: detour / unneeded action candidates → removed automatically (reversible marks), logged
4. SEGMENT      named SUBGOALS (hierarchical); boundary candidates from code, boundary decision by an L1 Noul
5. INDUCE       L2: acceptance predicate FIRST (independent of the code), then code skill + intent card
                classify every value: required input / fixed boundary / observation / assumption
                building → blueprint + generic buildBlueprint call
6. GAPS         full: L2 fills gaps itself (memory + similar skills + evidence), writes assumptions into the card, reports
                consult: L2 asks follow-up questions (with timeout); if unanswered, behaves like full
7. VERIFY       unseen terrain, materials, orientations and missing preconditions (counterexample factory), N replays;
                success = the predicate in the intent card; on failure: error + recording evidence → L2 repair (≤ 3 rounds)
8. DECIDE       Save / Update existing skill (new version) / Discard — full: automatic from the verification score;
                consult: proposal + timed approval. Always reversible later (a correction becomes a lesson)
9. LIBRARY      source=demonstrated, link to the recording, verification score, version
```

- **Value:** learning in **one demonstration** the skills an agent struggles to discover alone (building, farming, redstone, routes, combat tactics). Voyager's curriculum skipped these as "needing visual verification"; here the final state of the recording defines the success predicate.
- **"Exact packets" is not "exact intent":** a placement request may have been rejected; the player may have put the table next to the tree by accident. The raw recording is always kept; L1 cleaning is a reversible marking.
- **Phased delivery (decision 2026-10-15):** **v1** = a deterministic **blueprint** (from the server-side block diff, no LLM) + a named subgoal macro from events. **v2** = behavioral skills (farming, combat tactics) as parameterized code via L2, verified on unseen terrain. Both are in scope; v2 builds on v1. The proxy is validated first in spike S6.

---

## 5. Architecture: a game-independent core + game plugins

Decision: the system will **evolve to other games**. **Minecraft is a plugin**; the core knows no game.

### 5.1 Big picture

```
┌────────────────────────────────── CORE / HOST (game-independent, Python) ──────────────────────────────────┐
│                                                                                                            │
│  Autonomy engine (§5.6)    orchestrator · task-graph runtime (§9) · escalation ladder (§6.3) · decision log │
│  Action arbiter (§6.4)     single action owner · priorities · resource ownership · interrupt acks           │
│  Model layers (§6)         L1 DecisionClient (Jev / local) · L2 LlmClient (Sonnet / Haiku) · L3 training    │
│  Skill system (§8)         library · contracts · lifecycle · test runner · retrieval + L1 rerank            │
│  Memory (§7)               places · resource state · storage · event log + RAG · lessons and decisions      │
│  Recording (§4)            abstract → clean → segment → induce → verify (game-independent stages)           │
│  Persona (§10)             persona · mood · narration · diary                                               │
│  Evaluation + telemetry    test sets · ablation runner · S1-Bench · token/$/ms · trace ids                  │
│  UI shell                  CLI · web dashboard (plugins add panels) · voice (STT/TTS)                       │
│                                                                                                            │
└─────────────────────────────────────────┬──────────────────────────────────────────────────────────────────┘
                                          │  Game Plugin Protocol (versioned JSON-RPC, always a separate process)
        ┌─────────────────────────────────┼──────────────────────────────────┬────────────────────────────────┐
        ▼                                 ▼                                  ▼                                ▼
 minecraft plugin (A)            doom plugin (A, after delivery)    retro plugin (A, RAM reading)   desktop-pixel plugin (C)
 TypeScript · Mineflayer         Python · ViZDoom                   Python · stable-retro / PyBoy   screen + input · Jev Box · NitroGen
```

The core is extensible beyond games too:
- **Model providers:** Jev, local Unsloth models, Claude…
- **Memory backends**
- **Voice engines:** Whisper, TTS
- **UI panels**
- **Persona packs**

### 5.2 The game plugin contract

A plugin consists of a **manifest** (static description) and **components** (running parts).

**Manifest** (example fields):

| Field | Minecraft example |
|---|---|
| `id`, `version`, `protocolVersion` | `minecraft`, `0.1.0`, `gpp/1` |
| `game` + supported version range | Java Edition `1.21.11` |
| Integration level | `A` (state API) |
| Skill language / runtime | TypeScript (isolated execution process) |
| Capabilities | `predicates, knowledge, scenario, record, memoryExtractors, visibility` |
| Coordinate space | `xyz + dimension(overworld|nether|end)` |
| Safety defaults | Protected blocks, forbidden actions, limits |

**Components** (what the plugin provides to the core):

| Component | Provides | Used by |
|---|---|---|
| **Runtime adapter** | `observe`, `act`, `runSkill`, `interrupt`, `reset`, event stream | Executor, L1 monitor |
| **Primitive catalog** | Typed primitives + simplified signatures and examples for the LLM | L2 code writer, task graph |
| **State schema + projections** | Which state fields go to which L1 question; numeric/geometric precomputation ("zombie: 3.2 blocks, 40° left") | L1 DecisionClient |
| **Predicate library** | `inventory.has`, `isNight`, `insideEnclosure`… | Verifier, task-graph conditions |
| **Knowledge provider** | Goal → requirement graph (Minecraft: recipe tree → `obtain` solver), feasibility checks | Curriculum, L2, task compiler |
| **Vocabulary** | Place types (village, portal, mine…), entity/item ontology, danger types | Memory, L1 criteria |
| **Memory extractors** | Place / resource / episodic candidates from events | Memory |
| **Visibility filter** | Fair mode (line of sight) vs full-knowledge mode (§11) | Observation, memory |
| **Scenario builder** | Programmatic state setup (MC: `/give`, `/tp`, `/summon`, `/fill` via RCON) | Skill tests, synthetic data (L3), evaluation |
| **Recorder** | Turns a human demonstration into a semantic event stream (MC: protocol proxy) | Recording pipeline |
| **Starter skills** | Hand-written core skills + `obtain` (§8.4) | Skill system |
| **L1 question pack** | Game-specific criteria for the core's generic question templates | Question registry |
| **Prompt fragments** | The game's API, rules and tips for L2 | LlmClient |
| **Command vocabulary** | Short commands like `#mine`, `#goto`, `#follow` → skills | Task compiler |
| **Persona flavor** (optional) | Game-specific lines and reactions | Persona |
| **UI panel** (optional) | prismarine-viewer 3D view | Web dashboard |

**Runtime protocol:**

| Method | Purpose |
|---|---|
| `handshake()` | Manifest + protocol version + capability negotiation |
| `observe(projection?)` | Structured state (JSON) + optional frame; numeric/geometric work is done here |
| `act(primitive, args)` | A single primitive (for L0/L1 decisions) |
| `runSkill(code, deps, timeoutMs)` | Runs skill code in the plugin's isolated executor; returns events + result |
| `interrupt(reason)` | Interrupts the running skill and waits for an acknowledgement |
| `reset({ seed, mode })` | Reproducible start |
| `events` (stream) | Damage, death, inventory change, chat, block change… with sequence numbers |
| `checkPredicate(pred)` *(capability)* | Deterministic predicate |
| `knowledge.requirements(goal)` *(capability)* | Requirement graph / feasibility |
| `scenario.setup(spec)` *(capability)* | State setup for tests or synthetic data |
| `startRecording()` / `stopRecording()` *(capability)* | Demonstration capture |

**Thin mandatory core, optional capabilities:** every plugin must implement `handshake, observe, act, runSkill, interrupt, reset, events`. Everything else is an **optional capability**; the core turns a feature off when a plugin lacks it (a pixel plugin may have no exact predicates or reset). The contract first matures as interfaces inside the Minecraft plugin and is then tested against a second game (spike S8).

**Why a process boundary?** Skill code must run in the game's own language (Minecraft → Node, ViZDoom → Python, Unity mods → C#). A plugin is **always a separate process**. If an LLM-written synchronous loop locked an in-process event loop, the core, the L1 monitor and telemetry would all stop with it.

**Skill execution isolation:** inside the plugin, skill code runs in yet another **executor process/worker**:
- No API keys; restricted file and network access; CPU and memory limits.
- Game actions go only through a permission-checked **primitive broker**; every primitive call checks for cancellation.
- An external watchdog kills the executor on a hang and keeps or re-establishes the bot connection.
- Static rules: loops without `await` are forbidden; game commands via `bot.chat('/…')` are forbidden; no `require` / `process` access. Skills are TypeScript and must pass `tsc`.
- The agent's bot is **not an operator** on the server. Scenario setup and resets happen only through the evaluator's **RCON** connection.
- Node documents that `vm` is not a security mechanism and that its timeout does not cover async work ([Node vm](https://nodejs.org/docs/latest-v22.x/api/vm.html#timeout-interactions-with-asynchronous-tasks-and-promises)). A separate process is not a security boundary on its own either; it is meaningful together with the restrictions above.

### 5.3 Boundary rule: what goes in the core, what goes in a plugin?

| In the core (written once) | In a plugin (per game) |
|---|---|
| Orchestrator, task-graph engine, triggers | Primitives, command vocabulary |
| L1/L2 clients, escalation ladder, model routing | Game-specific L1 criteria, L2 prompt fragments |
| Question **templates** (danger, progress, mode, skill choice) | State projections for those templates |
| Skill library, contract schema, lifecycle, test runner | Skill code, scenario builder, predicates |
| Memory store, RAG, freshness, forgetting | Vocabulary, memory extractors, coordinate space |
| Game-independent recording stages | Recorder, raw → semantic event translator |
| Persona engine, mood | (optional) game-specific lines |
| Telemetry, evaluation runner, S1-Bench, training pipeline | Game-specific test tasks and metrics |

**Rule (also in AGENTS.md):** no game, block or item name appears in core code. If it does, it is in the wrong layer.

### 5.4 Technology choices

| Topic | Choice | Rationale |
|---|---|---|
| Core | **Python 3.13** (uv, ruff, pyright strict, pytest) | The owner's preference and learning language; the ML ecosystem is in the same language (TypeSafe Python SDK, Unsloth, Whisper, statistics, ViZDoom). Plugins are separate processes, so Mineflayer being JS does not affect the core. |
| Minecraft plugin | **TypeScript (strict), Node 22** | Mineflayer and skill code live in the JS world; skills are type-checked with `tsc` |
| Plugin protocol | Versioned JSON-RPC (stdio/WebSocket), **separate process**; thin mandatory core + optional capabilities | Language independence + isolation |
| L2 LLM | `LlmClient`; **Claude Sonnet 5.5 by default**, Haiku 5.5 for high-volume text; cascade and Opus measured in S5 (§6.8) | Quality first; routing proven by measurement |
| L1 | `DecisionClient` (§6.5): Jev + Unsloth decision model + logit readout + NLI + rules | Chosen per decision point by measurement (§6.6) |
| Embeddings | Local (on `fatih-pc`) | Free, fast |
| Storage | SQLite (+ sqlite-vec if needed) | Simple, local |
| **Parts borrowed from Mindcraft** | Not built on top of it; selected parts go into the Minecraft plugin: tested skills and world helpers (primitives + starter skills), patches to Mineflayer plugins, the ViaProxy setup, the task JSON format. MIT license; every borrowed file is recorded with its source and version | Shortens infrastructure work without breaking "the core knows no game". Tested together in spike S1 |
| Minecraft plugin stack | mineflayer 4.39.x, MC Java **1.21.11** pinned; Docker `itzg/minecraft-server` (offline, fixed seed, localhost, RCON); `minecraft-protocol` recording proxy; isolated skill executor + primitive broker + watchdog; prismarine-viewer panel | Tested versions; compatible with Mindcraft and the MCP server; runs without installing Java |

### 5.5 Evolving to other games, and multi-agent

- **Plugin order** (each tests the core's generality along a different axis):
  1. **minecraft** (A, TypeScript): the first prototype, aiming for "perfect".
  2. **doom** (A, **Python**, after delivery): a different language and real-time action; directly comparable with the Jev Doom experiments.
  3. **retro** (A, RAM reading; Game Boy/NES via stable-retro / PyBoy): 2D, a different coordinate space, SpeedrunBench and Pokémon comparisons.
  4. **desktop-pixel** (C): any game without an API. Perception through Jev images/Box + a VLM, possibly NitroGen as the reflex policy. The Cradle path.
- **Health metrics:** "core lines changed ≈ 0" alone is misleading, because an overly generic JSON interface also gives zero changes and pushes complexity into plugins. We track **plugin development time**, **duplicated code** across plugins, the **escape hatches** needed, and **behavioral parity** on the same task. Early contract changes are not failures; when a change is needed it is a contract gap and the contract is versioned (`gpp/1` → `gpp/2`) while old plugins keep working.
- **Conformance kit:** automatic tests every plugin must pass (handshake, observation schema, interrupt latency, predicate correctness, reset reproducibility). A plugin author never needs to read the core.
- **Cross-game transfer:**

  | Transfers | How |
  |---|---|
  | Model layers, routing, autonomy engine, memory engine, persona | Directly (core) |
  | L1 question templates | Directly; criteria come from the plugin |
  | **Shared skill concepts** | Abstract intents (gather, go, fight, flee, store, build, explore) map to concrete skills in each plugin. Pipelines and lessons written with these concepts transfer to other games. |
  | L1 decision models | A shared base model + per-game fine-tuning (§6.7); for a new game, start cold with the base model or Jev |
  | Lessons | Game-general ones ("after a big loss, secure safety first") transfer; game-specific ones ("creepers approach silently") stay in the plugin |

- **Multi-agent extension (future, decision 2026-10-15):** several bots in the same world dividing work (one mines, one farms, one builds) and coordinating. References: Mindcraft's MineCollab (communication cost: up to 15% drop when detailed plans must be exchanged), Project Sid's PIANO (concurrent modules, 1000+ agents), MindForge (theory of mind), PillagerBench (competitive teams). Design implications that we keep open from the start:
  - The core's identities are **per agent** (agent id on every trace, memory record and decision log entry).
  - Memory is split into **private** (per agent) and **shared** (world map, chests, claims) stores.
  - The action arbiter is per agent; a **world-level coordinator** handles task allocation and resource claims ("I am mining this vein") to avoid two bots competing for the same goal.
  - Inter-agent messages are structured (task offer, claim, status, help request), not free chat, to keep the communication cost low.

  Not scheduled before delivery; it comes after the Doom plugin unless time allows.

### 5.6 Autonomy levels: "never ask" is an option

Decision: the bot must be able to decide fully autonomously. **"Never ask" is an option**, not the only behavior. The user selects the level as a default, per task or per pipeline.

In the literature this maps to Feng et al.'s "Levels of Autonomy for AI Agents" ([arXiv 2506.12469](https://arxiv.org/abs/2506.12469)): autonomy is a **design choice** independent of capability. Full autonomy is considered suitable for low-stakes, speed-critical work ([source](https://concepts.dsebastien.net/concept/human-out-of-the-loop/)); a Hugging Face team argues against fully autonomous agents ([summary](https://aiweekly.co/node/9510)). A selectable level serves both views.

| Level (setting) | Feng level | When does the bot ask? | If no answer |
|---|---|---|---|
| **`full`: fully autonomous** | L5 Observer | **Never.** Don't ask → decide → log → report | — |
| **`approver`: asks for risky actions** | L4 Approver | Only predefined risky cases: irreversible actions, work near protected areas, spending valuable items | After the timeout (e.g. 30 s) the risky step is **not performed**: it is skipped, an alternative is chosen, or the task ends safely. **A timeout never grants permission.** |
| **`consult`: consults** | L3 Consultant | Ambiguous commands, gaps after a recording, plan approval before a long task | After the timeout → autonomous decision (within policy) |

**Core rule: a question never blocks the bot.** In `approver` and `consult`, every question has a **timeout** and a **default answer** (the bot's own decision). While waiting, the bot stays in a safe behavior (defend, wait); when the timeout expires it continues with its own decision. Even the most consultative mode never gets stuck while AFK. **Communication preference and permission are separate:** the autonomy level only decides *when to ask*; policies decide *what is allowed*. A timeout never permits something a policy forbids.

**Suggested defaults:**
- AFK / pipeline tasks: `full`.
- Teaching (record a skill): `consult`; the player is present, so follow-ups make sense.
- Early trust-building: `approver`.
- Overridable per task: `#mine iron 64 --autonomy=full`.

**Behavior by level:**

| Situation | `full` | `approver` | `consult` |
|---|---|---|---|
| Ambiguous command ("bring iron": how many? from where?) | Picks the most plausible reading (L1 Choice + past preferences + context), logs the assumption and reports it | Like `full` | Asks "how many?"; on timeout like `full` |
| Starting a long AFK task | Reads the plan back for information and starts at once | Like `full` | Reads back and asks for approval; starts on timeout |
| Irreversible action | Pre-set policy decides; if not allowed it is not done and an alternative is sought | **Asks**; on timeout not done (alternative or stop) | Asks; on timeout not done |
| Neither L1 nor L2 is confident | Safe default (stop, defend, retreat) | Like `full` | Asks a short "should I do X?", stays safe while waiting |
| Skill from a recording | Reports assumptions instead of follow-ups; decides Save/Update/Discard from the verification score | Like `full` | Asks follow-ups (§4.6 step 6); proposes Save/Update/Discard; on timeout like `full` |

**Four safeguards at every level:**
1. **Pre-set limits:** player rules ("don't break my house"), protected areas, task guards and budgets, plugin safety defaults. In `full` these replace approval.
2. **Prefer reversible actions:** with equal utility the reversible option wins; irreversible actions need a higher confidence threshold.
3. **Decision log:** every important decision is written with its reasoning, assumptions, confidence and, if asked, the question, answer or timeout.
4. **Emergency stop and later correction:** `#stop` works at any time. "You did that wrong" becomes a lesson/preference in memory.

**Measurement:** "questions = 0 in `full`" is true by construction, so it is not a metric. We measure **wrong assumptions**, later corrections and irreversible actions in `full`, and question count, answer rate and timeout rate in the other modes.

### 5.7 Improvements over Voyager

1. **Emergency reflexes in L0 plus an event-driven L1:** the bot reacts to danger while skills run → survival on easy/normal.
2. **Deterministic verification first** (independent predicates), then an L1 Noul, an LLM critic last → cheaper and more reliable.
3. **Feasibility checks** (the plugin's knowledge provider) → no invented tasks.
4. **Lessons from failure** (MineEvolve's remedy idea).
5. **Record a skill** → the building and placing skills Voyager skipped.
6. **Library hygiene:** versioning, duplicate detection, regression runs (skill drift), repair through candidate versions.
7. **Isolated execution, timeouts and acknowledged interrupts.**
8. **Measurement built in** (tokens, $, ms and trace ids on every call).
9. **A game-independent core:** Voyager was welded to Minecraft; here Minecraft is a plugin.
10. **Selectable autonomy:** no questions in `full`; timed questions in the other modes, never blocking.

---

## 6. Model layers: integrating Jev and frontier LLMs

Core principle: **every decision is made by the fastest and cheapest layer that is good enough.** A higher layer is used only when the lower one is not confident. Budget is not a constraint, but in a real-time game latency is a harder constraint than cost, and cost is measured anyway for the report.

### 6.1 Four layers

| Layer | Who | Latency | Frequency | Used for |
|---|---|---|---|---|
| **L0 reflex** | Plain code | 0–10 ms; emergency event → action ≤100 ms | every tick | Pathfinding, aiming, distances/angles, recipe chains (`minecraft-data`), predicates, state extraction, **emergency reactions**. Things a model never does. |
| **L1 System 1** | **Jev** / local decision model | p95 ≤300 ms | **event-driven**, one request in flight (in practice ≤ ~2–3 Hz) | Small, typed, contextual decisions: choose, yes/no, score. Not emergency decisions (those are L0). |
| **L2 System 2** | **Frontier LLM**: Sonnet 5.5 by default, Haiku 5.5 for high-volume text (§6.8) | 2–60 s | a few times per task | Writing and repairing code, planning, curriculum, skill induction from recordings, failure analysis |
| **L3 offline** | Frontier LLM + training | minutes–hours | between sessions | Labeling L1 data, synthetic scenarios, fine-tuning, library maintenance, evaluation |

**One latency budget:** emergency event → action ≤100 ms (L0, 1–2 ticks); L1 decision p95 ≤300 ms; tactical decision end to end (event → observation → decision → interrupt → server applies the action) p95 ≤500 ms; L2 calls are asynchronous and never block the reflex path. All other latency numbers in this document refer to this definition.

### 6.2 Decision-point map

| # | Decision point | Layer | Primitive / output | Why this layer | Fallback |
|---|---|---|---|---|---|
| 1 | Is there danger? (mob, fall, lava, drowning) | **L0** (L1 in shadow) | Rule + timer; an L1 Noul only in shadow mode or for **unknown** entities/situations | A numeric decision; Jev is weak with numbers and 300 ms is too slow for an emergency | — |
| 2 | What to do in danger? | **L0 first response**, **L1 tactics** | L0 flees/defends immediately; then an event-driven L1 Choice {continue, retreat, fight, eat, shelter, ask L2} | The first 100 ms belong to code; contextual tactical choice to the model. Value test in S4 | L0 rule; safest option on low confidence |
| 3 | Control mode (gather / explore / fight / stuck / wait) | **L0** state machine (L1 in shadow) | L1 Choice as a suggestion only | In Blocks.ai, too, **engine data** selected the phase and the model only chose the local direction | — |
| 4 | Making progress or stuck? | **L1** | Noul (last N observations + task) | Continuous monitoring; when stuck, triggers an L2 replan | L0 counter (position/inventory unchanged) |
| 5 | Which skill? (retrieval + rerank) | L0 + **L1** | Embedding top-20 → Choice + a per-skill "does it fit?" Noul | TypeSafe skill-suggestion recipe: wrong loads 16.8% → 7.3% | Embedding only |
| 6 | Player command ("bring me wood") → skill + arguments | **L1** | Choice (skill) + argument choices | Instant response in companion mode; code extracts argument candidates, the model chooses | L2 |
| 7 | Is the task done? (no deterministic predicate) | L0 → **L1** → L2 | Predicate → Noul → LLM critic | Cheap to expensive | — |
| 8 | Curriculum: which task next? | **L2** generates, **L1** scores | L2 proposes 10 candidates → Score (difficulty, novelty, utility) → code picks | Generation needs creativity; scoring is fast and parallel | L2 picks itself |
| 9 | Write / repair skill code | **L2** | Code | Only a strong code model can (Voyager, MindForge findings) | A stronger L2 model |
| 10 | Long-horizon plan (diamond → subgoals) | **L2** | Structured plan | Needs reasoning | — |
| 11 | Failure analysis → lesson (remedy) | **L2** | Text + tags | Needs explanation and generalization | — |
| 12 | Recording: narration sentence type | **L1** | Choice {instruction, rule, correction, chatter} | Many short sentences; fast and cheap | L2 |
| 13 | Recording: is this a subgoal boundary? | L0 candidate + **L1** | Noul | Many candidates, small decision | L2 |
| 14 | Recording: skill + intent card + assumption list | **L2** | Code + card | Synthesis work | — |
| 15 | (Level-C games) where is the target on screen, did the frame change? | **L1** | Box (Jev 1.14), image Noul | Fast visual decision | VLM (L2) |
| 16 | Memory writes: worth remembering? same as a known place? contradicts a record? | L0 candidate + **L1** | Noul ×3 | Frequent, small decisions (§7.2) | L0 rule (distance threshold) |
| 17 | Which resource / target to go for? (known mine, new cave, explore) | **L0** utility + **L1** choice | Choice | The arithmetic is code; the contextual choice is the model's (§7.3) | Highest L0 utility |
| 18 | Is Haiku enough, or Sonnet? (only if the cascade wins S5) | **L0** rule (+ L1 only as a threshold) | Rule; Jev Score calibration is numerically weak, so only as a threshold | Pre-routing (§6.8) | Sonnet |

**Value test (rule):** every L1 decision point is compared against a hand-written L0 rule for the same decision. In `jev-plays-doom`, Jev scored **the same** as a hand-written aiming rule; at such a point the model only adds latency and a dependency, so the decision stays in L0. The model must add value in **semantic** cases the rule misses (a new enemy type, unusual terrain, an ambiguous player command), and this must be shown by measurement. New L1 points start in **shadow mode**: they propose but do not act, and disagreements with L0 are logged.

### 6.3 Escalation ladder

```
Is the L0 rule decisive? ──yes──► act
   │ no / no rule
Ask L1 ──confidence ≥ τ(question, provider, version, projection)──► act
   │ low confidence
Ask L1 again: shuffled options + a different provider (Jev ↔ local) ──agree──► act
   │ disagree / still low
Safe default (stop, defend, retreat) + ask L2 asynchronously
   │ when L2 answers
act; (state, questions, L2 answer) → L3 training data
```

- **In `full` mode the human is not a rung of this ladder** (§5.6). The last rung is a safe default + asynchronous L2. In `approver`/`consult` a timed question to the human can be added; on timeout the same last rung applies.
- Thresholds are **measured** per `(question, provider, model version, projection)`. Confidence values are not comparable across providers (Unsloth also warns that thresholds do not transfer). Agreement between two providers is not correctness; shared errors are measured separately.
- According to TypeSafe's docs, confidence is not "permission to act"; it only describes how concentrated the distribution is.
- **Option-order effect** (a known Jev weakness): critical questions are asked twice with shuffled options (the self-consistency recipe).
- **Freshness check:** if the state has changed meaningfully when an L1 answer arrives (the enemy died, position moved 3+ blocks), the answer is discarded.

### 6.4 Runtime integration

```
            ┌───────────── Orchestrator (task loop, async) ─────────────┐
            │                                                           │
  L2 request queue ◄── replan / write code / repair ◄────────┐          │
  (asynchronous, cancellable)                                │          │
            │                                                │          │
            ▼                                                │          │
  Action arbiter ── runSkill / act ──► Plugin (isolated executor) ──► game
            ▲                            │ events (sequence numbers)    │
            │ proposals                  ▼                              │
  L0 safety reflexes (≤100 ms)  +  L1 decision loop (event-driven, one in flight)
     observe() → state projection → question pack (one request, parallel) ──┘
     → answers + confidence → escalation ladder → proposal: interrupt / continue / switch mode
```

- **L1 questions are asked in parallel in one request** (tactic, progress, skill fit). Jev answers independent questions in the same pass; extra questions cost only tokens.
- **L2 never blocks the reflex loop.** While L2 thinks, the bot stays in the safe behavior chosen by L0/L1.
- **Primitives are cancellable**, but cancellation is **cooperative**: pathfinder's `stop()` waits for the next node, and dig and collectblock have their own stop APIs. The primitive broker wraps each with its own stop path and waits for an **interrupt acknowledgement**. Voyager had none of this; the bot was unresponsive until the code finished.
- **Single action owner (action arbiter):** skills, L0 reflexes, L1 decisions and pipeline triggers do not drive the bot directly; they **propose**. The arbiter picks one owner by explicit priority (emergency safety > player command > trigger > task), manages resource ownership (movement, hands, inventory) and **discards** late results of interrupted work (job id / generation number). Before "continue", preconditions are re-checked. If night, low health and a full inventory trigger at once, a single "go home" plan runs.
- **State projection:** each question gets only the relevant fields (Jev degrades with long, irrelevant state). Distances, angles and counts are computed in L0 and given **ready-made** ("zombie: 3.2 blocks, 40° left"); the model never does arithmetic.

### 6.5 One interface: `DecisionClient` + question registry

- **`DecisionClient`** mirrors TypeSafe's request shape (state + questions → typed answers + probabilities + confidence). Providers:

| Provider | How | Note |
|---|---|---|
| `typesafe` | Jev 1.13 / 1.14, official SDK | API key available |
| `unsloth-local` | An Unsloth-trained decision model; its Decision API can route requests named `jev-latest` to the local model, with answers in Laya format | One-to-one compatibility with the TypeSafe SDK is **not verified**; a thin adapter may be needed |
| `logit-local` | The Blocks.ai method: base model, one forward pass, softmax over letter logits (MLX / llama.cpp) | No training needed |
| `nli-local` | GLiClass / DeBERTa-v3 NLI | Very fast, runs on CPU; for intent and narration classification |
| `llm-structured` | Frontier LLM with structured output | Accuracy upper-bound reference (slow) |
| `rules` | L0 rule | Baseline |

- **Question registry:** each decision point is a versioned **question definition**: `id`, instructions, criteria, state projection function, option-order policy, threshold, fallback, value-test result. Telemetry logs every call as `(question_id, version, provider, state, answer, confidence, latency, outcome)`. This log is the source of both the benchmark and the fine-tuning data.

### 6.6 System 1 model comparison: Jev or local?

**Candidates:**

| Candidate | Type | Expectation | Source |
|---|---|---|---|
| Jev 1.13 / 1.14 | Closed decision model | 70–500 ms, $0.042/Mtok; weak at counting and option order | TypeSafe docs |
| Unsloth decision model: Qwen3.5-0.8B / 2B / 4B, Gemma 4 E4B | LoRA + Clef-style classification head; probabilities + calibration (ECE) | 77–81% on general data (Unsloth's own report); the real gain should come from **fine-tuning on game data** | [Unsloth](https://unsloth.ai/docs/new/train-your-own-decision-model-with-unsloth) |
| Gemma 4 12B base + logit readout | Zero-shot | 113 ms median on an M4 Mac, no training | Blocks.ai |
| DiffusionGemma + vLLM patch | Open "Jev clone" | Roughly on par with Jev in early comparisons (unverified) | Secondary |
| GLiClass (modern-base / edge), DeBERTa-v3-large NLI | Zero-shot encoder | Very fast; strong at text classification, possibly weak at state reasoning | [GLiClass](https://arxiv.org/abs/2508.07662), [BTZSC](https://arxiv.org/abs/2603.11991) |
| Fine-tuned ModernBERT / DeBERTa encoder | With labeled data | 10–1000× faster than LLMs on a fixed label set, equal or better; does not generalize to new labels | [arXiv 2602.06370](https://arxiv.org/abs/2602.06370), [arXiv 2608.20371](https://arxiv.org/abs/2608.20371) |
| Claude Haiku/Sonnet 5.5 with structured output | Frontier LLM | Accuracy reference; slow for real time | — |
| L0 rule | Code | Baseline | — |

**Benchmark design (S1-Bench, per game):**
- **Data:** 200–500 states per decision point, from real game logs + synthetic scenarios (§6.7). Labels: rule-computable ones + outcome-based (counterfactual) ones + frontier-LLM teacher labels (spot-checked by a human). Consecutive states are not independent samples.
- **Metrics:** accuracy and macro-F1; **calibration** (ECE, reliability curve); p50/p95 latency on our hardware, cold and warm cache; option-order consistency; cost per call; miss rate and false alarms on rare dangers; **in-game impact** (survival and task success on the same seeds).
- **Decision rule:** pick the Pareto-best (accuracy × latency) provider per decision point; different points may use different providers (e.g. narration classification on `nli-local`, tactics on Jev or a fine-tuned Qwen).

### 6.7 Game-specific fine-tuning and synthetic data (data flywheel)

Games are ideal for synthetic data because **we own the simulator**: we can set up a state and measure the outcome.

```
1. SCENARIOS     L2 + code: set up random but meaningful states via RCON
                 (Minecraft: /summon, /tp, /effect, /time, /give: 2 zombies at 5 blocks, health 6, night, no sword…)
2. LABELS        a) rule / oracle (computable questions) — preferred
                 b) COUNTERFACTUAL (pilot on one decision point only): replay the same scenario with each option MANY
                    times and measure the outcome distribution (damage, death, progress); Minecraft is not
                    deterministic, a single trial teaches noise
                    WARNING: a "damage within 3 s" label depends on the chosen action (a correct escape makes a
                    dangerous state look "safe") → keep the danger label and the policy outcome separate
                 c) frontier-LLM teacher (with reasoning), spot-checked by a human
                 d) real game logs + hindsight outcomes
3. DATASET       Unsloth format: {state, questions, gold}; question definitions from the registry;
                 train / calibration (holdout) / test split; no seed or scenario leakage
4. TRAIN         Unsloth decision model (Qwen3.5 0.8B → 4B), LoRA r16, 2–4 epochs; calibrate() for ECE
5. SERVE         Decision API → `unsloth-local` in DecisionClient
6. COMPARE       S1-Bench + in-game A/B: Jev vs fine-tuned vs zero-shot
7. REPEAT        new failures → new scenarios (active learning: low-confidence / disagreeing states first)
```

- **Recordings feed in too:** the player's decisions in a demonstration (what they did in danger) are human labels for L1.
- **Distillation goal:** move L2's expensive but correct decisions (fuzzy verification, skill choice) into L1. The number of L2 calls should fall over time, which is a curve to measure in the report.
- **Hardware:** training and local serving on `fatih-pc`'s RTX 5070 Ti (16 GB) (§6.9).
- This overlaps with the course's **Model Distillation (#42)** project and can be presented as separate value in the report.

### 6.8 Frontier LLM (L2): Sonnet 5.5 by default, cascade measured

**Decision (2026-10-15, after review):**
- Default for writing and repairing code, planning and skill induction: **Claude Sonnet 5.5** (`claude-sonnet-5-5`).
- High-volume text work (summaries, diary, skill descriptions, memory reflection): **Claude Haiku 5.5** (`claude-haiku-5-5`).
- A **Haiku → Sonnet cascade** and **Opus 5.5** (`claude-opus-5-5`) are measured in **spike S5**. The cascade becomes the default only if it is not worse than Sonnet alone on success and is clearly better on time or cost. Opus is used for hard repairs and skill induction only if it clearly beats Sonnet there.

Rationale: the cascade's purpose was cost and speed; with no budget constraint, only speed remains, and a cascade adds both models' latency when Haiku fails and splits the prompt cache per model (both reviewers, §14).

The cascade design below is the **candidate measured in S5**. If it wins, it works with **pre-routing and post-hoc escalation**:

1. **Pre-routing (straight to Sonnet without trying Haiku):** work known to be hard goes directly to Sonnet; trying Haiku first only adds latency.
   - Fixed rules: skill induction from recordings, code repair after the 2nd failed attempt, long-horizon planning → Sonnet.
   - Additional signals: is there a similar skill, how many subgoals, how often this task failed before, is there a related lesson in memory.
2. **Post-hoc escalation (Haiku tried, result bad):** triggers must be **cheap and objective**. The model saying "I'm not sure" is not trusted.

   | Trigger | Checked by |
   |---|---|
   | Code does not parse, fails `tsc`, violates static rules, calls a missing primitive | L0 (compiler / AST) |
   | The plan fails feasibility (nonexistent item, missing recipe) | L0 (knowledge provider) |
   | The skill errors in the executor or fails **2 attempts** | L0 + verifier |
   | An L1 plausibility check rates Haiku's decision low | L1 Noul |
   | Two Haiku samples contradict each other (critical decisions) | Code |

3. **Learn by measuring:** every escalation is logged (trigger, Haiku result, Sonnet result, final outcome). **Signed Rescue Routing** ([arXiv 2609.07786](https://arxiv.org/abs/2609.07786); its abstract still lists results as "TBD", so treat it as a conceptual warning, not evidence) warns that a large model can also break the small model's *correct* answer. So the **net benefit** of escalation is measured per trigger, and triggers without benefit are removed. With enough data the router could become a learned model in L3 ([cascade routing, ICML 2025](https://icml.cc/virtual/2025/poster/46183); [routing/cascading survey](https://arxiv.org/abs/2603.04445)).

**Default assignment (decided; updated after S5):**

| Work | Default model | Note |
|---|---|---|
| Curriculum candidates, QA cache | Sonnet | Cascade candidate: Haiku first, Sonnet if feasibility fails |
| Simple skill code (known pattern, similar skill exists) | Sonnet | Cascade candidate: Haiku first, Sonnet on `tsc`/static errors or 2 failed attempts |
| Code repair (3rd attempt onward) | **Sonnet** | Opus candidate (S5) |
| Long-horizon planning, subgoal decomposition | **Sonnet** | — |
| Skill + intent card + assumption list from a recording | **Sonnet** | Opus candidate (S5) |
| Failure analysis → lesson | Sonnet | — |
| Memory reflection, daily summary, skill descriptions | Haiku | — |
| LLM critic (when predicates and L1 are not enough) | Sonnet | Never in the same class as verified success |
| L3 teacher labeling | **Sonnet** (with reasoning) | — |

- All models sit behind `LlmClient`; prompt caching is on (the system prompt and primitive docs are long and repeated).
- **S5 and the report ablation:** Haiku only / Sonnet only / Opus only / cascade → success, attempts, wall-clock time, total cost.

### 6.9 Hardware placement

Two machines: a **Mac** (development) and **`fatih-pc`** (NVIDIA **RTX 5070 Ti, 16 GB VRAM**).

| Work | Where | Note |
|---|---|---|
| Unsloth decision-model training | PC (5070 Ti) | Qwen3.5 0.8B / 2B / 4B fit comfortably (4–8 GB); Gemma 4 E4B (~14.4 GB) is tight |
| Local L1 serving, embeddings, Whisper | PC | Mac ↔ PC LAN latency is a few ms; fits the L1 budget (≤300 ms) |
| Minecraft server (Docker) + bot | Mac or PC | Recording uses the machine where the game client is installed |
| Jev, Haiku, Sonnet | Cloud API | — |
| Fallback when the PC is off | Mac | L1 falls back to Jev / rules; Whisper via `mlx-whisper` |

---

## 7. Game memory: a world map + RAG

Requirement: the bot should know its game history, inventory and past decisions, and at the very least **where home and the portal are**; it should remember where it saw villages and found things, and **never walk back to an exhausted mine for nothing**.

### 7.1 Key idea: memory is not one RAG

The answer to "where is my home?" is a coordinate; the answer to "should I go to that mine?" is a calculation. Finding these with vector search is slow and unreliable. Memory is therefore split by **query type**, and RAG is used only for free-text history:

| Memory type | Holds | Queried by | Layer |
|---|---|---|---|
| **Places** (spatial records) | Home, bed, portal (with its linked pair), village, mine, chest, farm, structure, danger zone: type, coordinates + dimension (overworld/nether/end), name, first seen, last visited, **last verified**, status (active / exhausted / destroyed / unknown), source (observed / player said / inferred) | **Structured queries in code** (L0): "nearest active village", "path cost home" | L0 |
| **Resource state** | Per region/chunk: ores seen (with positions), ores mined, estimated remaining, scanned volume | Code: expected yield / (travel + mining time) | L0 computes, L1/L2 choose |
| **Items and storage** | Chest contents (timestamped); "where is my iron?" | Code: item → list of chests | L0 |
| **Episodic memory** (event log) | What, where, when: "day 3, (x,y,z), found a village", "died to a creeper", "task X failed because of Y" + day/session summaries | **RAG**: hybrid search (BM25 + vectors) + filters (dimension, distance, time) | L1 ranks, L2 reads |
| **Semantic memory** (lessons and decisions) | Remedies, learned facts ("this world's desert temple is to the west"), **decisions with reasons** ("we left the eastern mine because it was exhausted") | RAG + tag filters | L2 |
| **Procedural memory** | The skill library (§8) | Embeddings + L1 rerank | — |
| **Player rules and preferences** | "Don't break my house", "this is home", "don't go out at night" | Always in context (small, prioritized list) | Enforced as L0 rules |

This split matches two lines of work:
- **MrSteve** ([ICLR 2025](https://arxiv.org/abs/2411.06736)) attributes Minecraft agents' failures to missing episodic memory and proposes a **what-where-when place-event memory**; the agent switches between exploring and solving based on recalled events.
- **EMem-Bench** ([arXiv 2609.28236](https://arxiv.org/abs/2609.28236), 2026-09) splits memory into spatial / event / scene. Current models are weakest at **tracking dynamic world state** and **recording state revealed by interaction**. "This mine is exhausted" is exactly the second kind.

### 7.2 Write path: what enters memory, and how

```
Plugin event stream + periodic scans (visible blocks, nearby entities)
   │
   ▼ L0 — rule-based extractors (automatic, cheap; in the plugin)
   │   village: villagers + bell + bed cluster     → place candidate (village)
   │   portal:  nether_portal blocks               → portal (pairs linked on dimension change)
   │   mine:    ore cluster + mining activity      → resource-state update
   │   death, damage, inventory delta, chest open/close → episodic event
   │
   ▼ L1 — small decisions (Jev / local)
   │   "Is this worth remembering?"                 (Noul, importance)
   │   "Is this the same place as known place X?"   (Noul, merge / dedupe)
   │   "Does this observation contradict a record?" (Noul → invalidation)
   │
   ▼ L2 — reflection (Haiku; rare)
       end of day / while sleeping / end of session: summarize events, extract lessons and decisions,
       annotate places ("this village has a blacksmith")
```

- **In fair mode only seen blocks are written** (§11): the bot cannot remember what it never saw.
- **The player can write directly:** saying "this is home" or `// home here` in chat records the location as `home` with source "player" and the highest confidence (the same channel as recording narration).
- **Resource state is the basis of "exhausted":** per region, ores seen − ores mined and the scanned-volume ratio. If no seen ore remains and coverage is high, the region becomes `exhausted`; with low coverage it stays `unknown`, separating "maybe more" from "definitely gone".

### 7.3 Read path: how memory is used

1. **Structured queries** (L0, milliseconds): `nearest(type="village", status="active", dimension="overworld")`, `chestsContaining("iron_ingot")`, `portalPair(id)`. The planner calls them as **tools**, and skill code can call them too (`goTo(memory.home)`).
2. **Utility calculation** (L0): "I need iron" →

   | Option | Calculation | Result |
   |---|---|---|
   | Known mine A | 120 blocks away, ~2 ores estimated left | low utility |
   | Cave B | 60 blocks away, 8 iron seen, unmined | **high utility** |
   | Explore | expected value (biome, y level) | medium |

   L0 computes the table; L1 makes the choice (context: is it night, is the inventory full) or L2 if inside a long plan. **"Don't go to an exhausted mine" emerges naturally**; no separate rule is needed.
3. **RAG** (free-text history): "What happened in this area before?", "Why did we stop going east?" → hybrid search + filters → L1 rerank → the best few records.
4. **Context pack** (for L2 prompts): every L2 call gets a fixed-budget memory summary: key places (home, portal, active villages, best resource spots), recent events, related lessons, player rules. Code builds the pack; L1 orders it.

### 7.4 Freshness, contradictions and forgetting

- **Time-bounded validity:** every record has `valid_from` / `valid_to` + `last_verified`. Game memory is high-frequency, so it lives in its own local store.
- **Re-verification:** when the bot passes near a known place it checks it automatically ("is the portal still there?"). If an observation contradicts a record, the old record is closed and a new one opened; history is never deleted.
- **Conflict rule:** a newer **direct observation** wins. An inference cannot override an observation. Player-provided facts change only through a new observation.
- **Forgetting:** "Remember the Decision, Not the Description" ([arXiv 2605.10870](https://arxiv.org/abs/2605.10870)): memory should keep the **distinctions that change decisions**, not full descriptions of events. In practice:
  - Places and decisions are never deleted, only marked stale.
  - Old episodic events are compressed into day and week summaries.
  - Raw events that never fed a decision are dropped over time.

### 7.5 Generality: a game-independent memory core

- The core memory API does not know the game. A **place** = `{type, coordinates, space}`. The type vocabulary (village, portal, mine…) and the coordinate system (Minecraft: x,y,z + dimension; Doom: map + x,y; a 2D game: room + x,y) come **from the plugin**.
- L0 extractors live in the plugin (village detection is game-specific); the store, queries, RAG, freshness and forgetting stay in the core.
- Every record is tagged `game + world_instance_id + episode_id + reset generation`; **the seed is not an identity**, only metadata (two worlds built from the same seed diverge over time, and memory must not leak across resets). Worlds never share place memory, but **lessons** can transfer ("creepers are dangerous at night").
- With multiple agents (§5.5), records also carry an agent id and are either private or shared.

### 7.6 Measurement (for the report)

- **Memory tasks** (added to the test set; inspired by MineNPC-Task and EMem-Bench):
  - "Go back to the village you saw two days ago."
  - "Which chest did we put the diamonds in? Bring them."
  - "Go home through the Nether portal."
  - "I need iron" → must **not** go to the exhausted mine.
- **Metrics:** correct-return rate; **wasted trips** (count and distance to exhausted or vanished targets); unnecessary re-exploration; memory query latency.
- **Ablation:** memory off / RAG only / structured only / structured + RAG. Expectation: "RAG only" fails location questions, which is the evidence for this design.

---

## 8. Skill design: the real source of speed

Thesis: **with really good skills, everything gets dramatically faster.** The evidence supports it:
- **SkillsBench** ([arXiv 2602.12670](https://arxiv.org/abs/2602.12670)): curated skills raise the average pass rate from 33.9% to 50.5% (+16.6 points). **Focused skills with at most three modules** beat large, exhaustive bundles. Small models with skills can match larger models without them.
- **Skill selection:** in a 196-skill library, loading everything gave 29.3% while a task-conditioned composer reached 45.3% with fewer tokens ([arXiv 2606.32025](https://arxiv.org/abs/2606.32025)).
- **AgentSkillOS** ([arXiv 2603.02176](https://arxiv.org/abs/2603.02176)): with the same skills, organizing them as a DAG clearly beats flat invocation.
- **SkillEval** ([arXiv 2608.06891](https://arxiv.org/abs/2608.06891)): skill quality has two sides: fit to the task and reusability.

### 8.1 Skill hierarchy

```
Level 4  ROUTINE / PIPELINE   user-level orchestration (§9): "while AFK, mine iron, empty when full"
Level 3  COMPOSITE SKILL      build a shelter, iron armor set, wheat farm, go to the Nether
Level 2  BASIC SKILL          obtain(item, n), mineOre(type, n), smelt(item, n), goTo(place), fightOrFlee()
Level 1  PRIMITIVE            the plugin's hand-written, tested core (~15–40)
Level 0  REFLEX               pathfinder, pvp, aiming (Mineflayer plugins)
```

**The biggest accelerator: a general `obtain(item, n)` solver.** It works over the `minecraft-data` recipe graph (similar to GITM): what is in the inventory and what is missing; which sub-items the missing ones need (recipe tree); which tools are required; where raw materials are (resource state first, otherwise exploration). **Code** computes all of this and calls primitives in order. The hundreds of "craftX / mineY" skills Voyager had the LLM write one by one collapse into one deterministic solver; the LLM is left with what the solver cannot do: building, tactics, unusual situations.

Note from the review: this is not a small helper but a **planner** in its own right. The first version supports a finite set of items; alternative recipes, fuel, tool durability, station access and inventory capacity are handled explicitly; there is cycle detection, resource reservation and explicit `unsupported` / `unreachable` results.

### 8.2 The contract of every skill

| Field | Example |
|---|---|
| Name + description (in task language) | `buildShelter`: "Builds a closed 5×5 shelter for the night" |
| Parameter schema | `{ size: 3–7, material?: blockName, near?: placeRef }` |
| Preconditions | ≥ 40 blocks, open space |
| **Postcondition (deterministic predicate)** | The bot is inside a closed volume; there is a door. Written **before and independently of** the code, tested against negative examples (no roof, unreachable door, enemy inside, pre-existing structure); if undecidable the result is `unknown`, never success |
| Side effects | Consumes blocks, places blocks, adds a place record (`shelter`) |
| Typed failure kinds | `missing_items`, `not_found`, `path_blocked`, `interrupted`, `timeout`, `unsafe`, `unsupported` |
| Cancellable | Honors cancellation; goes to a safe state when interrupted |
| Resumable | Continues a half-built shelter |
| Risk level + expected duration | Used by the pipeline planner and L1 |
| Dependencies | Sub-skills it calls (DAG) |
| Source | Hand-written / learned / demonstrated / promoted from a pipeline |
| Metrics | Success rate, mean duration, failure distribution, usage count |

### 8.3 Skill lifecycle

```
draft ──(scenario tests, parameter jitter: N/N)──► verified ──(k successful real uses)──► trusted
  ▲                                                  │                                     │
  └──── repair as a CANDIDATE version (L2) ◄── failure / version change (skill drift) ◄────┘
                                                            unused / duplicate → retired
```

- **Retrieval and use** see only *verified* and *trusted* skills by default.
- **Repairs never overwrite a working skill:** a repaired version is a candidate and becomes active only after it passes the regression suite.
- **Scenario tests:** small test worlds set up over RCON (`/give`, `/tp`, `/fill`) + the postcondition predicate. **Regression** runs nightly and on every version change.
- **Skill contribution:** "success with the skill − success without it" is measured (the "Skill Lift" idea from NVIDIA SkillEvaluator). Skills that add nothing are simplified.
- **Merging and simplifying duplicates:** refactoring with rollback validation, as in Programmatic Skill Networks ([arXiv 2601.03509](https://arxiv.org/abs/2601.03509)).
- **Few, focused skills in context:** at most 3–5 relevant skills per L2 call, in dependency order (SkillsBench + composer findings).

### 8.4 Starter library (bootstrap)

As in ODYSSEY, we start from a **hand-written core**: primitives + the `obtain` solver + ~20 basic skills (fight/flee, eat, sleep, store/take from a chest, go home, explore, chop a tree, find a cave), partly borrowed from Mindcraft. Learning and recording build **on top of** this core; trying to learn everything from scratch was Voyager's expensive, slow path.

**Measurement for the report:**
- Time and LLM calls to reach a diamond pickaxe in three arms: from scratch / with the core / core + learned library.
- **LLM calls per hour** should fall as the library grows: direct evidence that skills speed the system up. Reported as a slope with a confidence interval, not as "monotonic".

### 8.5 Four skill sources, one standard

| Source | How it arrives | Same contract and tests |
|---|---|---|
| Hand-written | Developer | ✓ |
| Learned | The Voyager loop (L2 writes code) | ✓ |
| Demonstrated | Record a skill (§4) | ✓ |
| Promoted from a pipeline | A frequently used pipeline compiled into a skill (§9) | ✓ |

---

## 9. Commands, tasks and pipelines (AFK mode)

Requirement: "I played, now I'm going AFK; I should be able to tell the bot *go mine*, *kill enemies*, *find this*", through natural language, voice, or by building a pipeline.

### 9.1 Three input channels, one intermediate representation

```
 Natural language (in-game chat / web) ─┐
 Voice (push-to-talk → Whisper)          ─┼──► TASK GRAPH (Task IR) ──► validate ──► read back ──► execute ──► report
 Pipeline (visual editor / YAML)         ─┘          ▲                                                  │
                                                     └────────── save / schedule / promote to skill ◄───┘
```

**Task graph (Task IR):** a small, typed behavior tree / DAG.

| Node | Meaning | Example |
|---|---|---|
| `skill(name, params)` | Skill call | `mineOre("iron_ore", 64)` |
| `sequence` / `fallback` | Do in order / use the first that succeeds | Look in the chest first, otherwise mine |
| `loop(until | count | duration)` | Repeat | Until the inventory is full |
| `condition(predicate)` | State or memory query | `night`, `health < 6`, `inventory.full`, `memory.exhausted(mine_A)` |
| `trigger(event → subgraph)` | Event trigger | At night → go home, sleep; inventory full → empty into chest X |
| `guard` | Limits | Stay within 200 blocks of home, never touch player builds, risk ≤ medium |
| `budget` | Time / distance / attempt limit | At most 2 hours |
| `report` | Notification policy | Summary every 15 min, notify on done/failure |

**Example:** "I'm AFK; mine 64 iron, go home and empty into the chest if the inventory fills, sleep at night, run home if health drops below 6, finish within 2 hours"

```
budget(2h) ▸ guard(radius=200 from home, protect=player_builds)
  ├─ trigger(night)          → goTo(home.bed) ▸ sleep
  ├─ trigger(health < 6)     → fleeTo(home) ▸ eat ▸ wait(health ≥ 14)
  ├─ trigger(inventory.full) → goTo(chest:"mine chest") ▸ deposit(ores)
  └─ loop(until mined(iron_ore|raw_iron) ≥ 64)     ◄ counts total acquired, not what is currently held
        └─ mineOre("iron_ore")   ◄ the target is chosen from resource state (never an exhausted mine, §7.3)
report(every 15m, on: done | fail | death)
```

### 9.2 Compiling a command into a task graph

1. **Deterministic parser first.** Baritone-style short commands (`#mine iron 64`, `#goto home`, `#follow Fatih`, `#stop`) map straight to a graph. No model, instant. (nekostulAICompanion also tries a strict parser first and falls back to an LLM.)
2. **Simple natural language → L1.** "Bring me wood" → Choice (skill) + argument choice, ~200 ms (decision point #6).
3. **Complex natural language / voice → L2** (Sonnet by default, §6.8) writes the task graph.
4. **Validation (L0):**
   - Do the skills exist, do the parameters fit the schema?
   - Do memory references resolve (which chest is the "mine chest")?
   - Feasibility: is there a pickaxe for 64 iron? If not, `obtain(stone_pickaxe)` is added to the graph.
   - Player rules and safety limits.
5. **Read back:** "Understood: 64 iron, into the mine chest when full, sleep at night, run home below 6 health, 2 hours." Read via TTS on the voice channel. In `full` mode the bot starts **without waiting** and reports its assumptions for ambiguous parts. In `consult` mode it asks for approval and starts on timeout. The player can correct it any time with `#stop` or a new command (§5.6).

### 9.3 Execution engine (game-independent)

- **The behavior-tree runtime lives in the core.** Triggers listen to the same event stream as the L1 monitor; when a trigger fires, it proposes to the action arbiter, the running skill is interrupted, the trigger's subgraph runs, and then the main loop resumes.
- **Persistent state:** pipeline state is written to disk. If the connection drops or the bot dies, it resumes; after a death a standard `recoverDeath` subgraph collects the dropped items.
- **Reporting:** in-game chat, the web dashboard, and optional phone notifications. On return, an **"AFK summary"**: what it collected, what it found where (what was written to memory), what went wrong.
- **Save and reuse:** e.g. a "morning routine" (harvest + cook + store), schedulable by in-game or real time.
- **Promotion:** a frequently used pipeline is compiled into a contracted, tested composite skill (§8.5).
- **Visual editor:** a node-based editor in the web dashboard (drag-and-drop triggers, conditions, skills). Skills from recordings appear as nodes too.

### 9.4 Prior art

- **Baritone** ([usage](https://git.psf.lt/0xf8/baritone/raw/branch/1.12.2/USAGE.md)): `#mine 64 diamond_ore`, `#goto`, `#follow`, `#farm`, waypoints. Proven command ergonomics, but no conditions, triggers or memory.
- **AIBot "Bob"** ([source](https://p.codekk.com/detail/6a033e245b02fc5c75bba05c)): "the LLM plans, deterministic tasks execute"; a backward-chaining goal planner + 44 independent state machines, each with its own watchdog. Very close to our L2/L0 split.
- **LLM-generated behavior trees** (robotics, [arXiv 2302.12927](https://arxiv.org/abs/2302.12927)): trees generated from natural language, with an interpreter that fixes the tree on failure.
- **Wingman AI:** a voice game companion (STT/TTS, command definitions).
- **Safety:** the AFK bot runs only on **our own server**; AFK bots can break other servers' rules.

---

## 10. Creativity and personality

### 10.1 Inspiration: GPT-6 Astra and the creeper incident (September 2026)

**What happened?** The independent evaluator **Vals AI** had OpenAI's GPT-6 Astra play Minecraft in a 141-hour stream, reportedly with standard controls only ([Dexerto](https://www.dexerto.com/minecraft/gpt-6-astra-forced-to-play-minecraft-gets-depressed-by-creeper-and-farms-potatoes-for-hours-3409634/), [Tom's Hardware](https://www.tomshardware.com/tech-industry/artificial-intelligence/defeated-gpt-6-astra-model-spent-several-hours-just-farming-potatoes-after-being-blown-up-by-a-creeper-in-minecraft-openai-offering-gets-further-than-any-other-ai-system-in-141-hour-test), [XDA](https://www.xda-developers.com/gpt-6-astra-made-amazing-progress-on-minecraft-until-a-creeper-blew-up-its-chest-and-it-spiralled-into-sadness/)).
- The model built a semi-automatic blaze farm and collected 6 blaze rods and 3 ender pearls.
- After it stored its valuables in a chest, a creeper blew up **the chest and the bed**; the spawn point was gone too.
- The model then spent hours **only farming potatoes**. Later it became wary of "green things"; it mistook sugarcane for a creeper and noted to itself "GREEN tall thing ahead was SUGARCANE, NOT creeper!"
- It wrote itself a note: keep critical items safe, never leave chests unguarded.
- The story went viral; OpenAI's developer account shared it.

**Correction:** the "waited to die" detail does not appear in the sources; what they describe is hours of potato farming. "Depression" is the media's interpretation. The model does not feel emotions, but people **read its behavior as an emotional story**, and that is what makes it valuable.

**Two lessons:**
1. **Engineering:** the agent had **no recovery plan** after a big loss and got stuck in low-risk, repetitive work.
2. **Product:** people read an agent's reactions as **personality**, and it draws a lot of attention. Gold for a demo video and a presentation.

### 10.2 Recovery: solving the post-loss plan as engineering

- **Detect a big loss (L0):** death, a chest or bed destroyed, valuable items lost (inventory + memory diff).
- **Post-mortem (L2):** what was lost (from memory), why, what the lesson is → semantic-memory rules such as "store valuables in an ender chest / wall in chests / keep the bed protected".
- **Recovery plan (L2):** a "fastest way back" graph: if the items can still be picked up, run for them first; otherwise a re-production order.
- **Stagnation detection (L1, decision point #4):** "have I been doing low-value repetitive work for N minutes?" → if yes, replan. Astra's potato loop is exactly this case.

### 10.3 Personality: an optional feature

The goal is to make the bot watchable as a "character". Rule: **personality never sabotages play**; the player's explicit commands always come first, and "work mode" turns it off entirely.

| Component | How |
|---|---|
| **Persona** | Name, speaking style, values ("curious explorer", "careful builder", "joker"). Prompt + small biases on L1 thresholds. |
| **Mood state** | Numeric variables derived from events and decaying over time: *confidence, fear, curiosity, boredom, pride*. Death → fear↑; rare find → pride↑; long repetition → boredom↑. |
| **Effect on behavior (bounded)** | High fear lowers the risk threshold (no going out at night). High boredom weights novelty in the curriculum (the opposite of Astra's potato loop). Effects are bounded in code and logged. |
| **Narration** | Short comments in chat / TTS: "This green thing… is sugarcane. Yes. Definitely sugarcane." Voice reactions at key moments. |
| **Diary** | At the end of each in-game day, L2 (Haiku) writes a first-person **diary** from episodic memory ("Day 3: nearly died in a cave…"); the human-readable face of memory. |
| **Shared history** | With the player: "Last time we died here together." The social use of memory. |
| **Highlights** | Telemetry flags "interesting moments" (narrow escapes, rare finds, big losses) → automatic clip timestamps for the demo video. |

Prior art:
- **Project Sid:** small prompt nudges produce distinct personality diversity ([MIT TR](https://www.technologyreview.com/2024/11/27/1107377/a-minecraft-town-of-ai-characters-made-friends-invented-jobs-and-spread-religion/amp/)).
- **MIMIC** ([arXiv 2510.01635](https://arxiv.org/html/2510.01635v1)): game agents optimized for task completion behave homogeneously and repetitively; personality traits diversify behavior.

### 10.4 Creativity: a bot that sets its own goals

- **Curiosity curriculum:** novelty score (L1 Score), unexplored biomes, items never made. Voyager's "maximize exploration" idea, tuned by mood.
- **Aesthetic building:** L2 designs a house that fits the terrain and biome → blueprint → `buildBlueprint` (reusing the blueprint machinery from §4).
- **Surprises for the player:** "I made you something" moments on return from AFK (a small tower, a marked path to a village). Only in personality mode and within player rules.
- **Notes to self:** like Astra's "protect critical items" note, learning lessons and changing its own behavior is already §7's semantic memory; in personality mode these notes also appear in chat.

---

## 11. The first prototype: playing Minecraft "perfectly"

**Decisions (2026-10-15):**
- **Main claim: learning by playing.** "A learned skill library reduces time and LLM calls in worlds the bot has never seen, without lowering success." Learning from demonstration and AFK reliability are reported as supporting results.
- **"Perfect" is tiered:**
  - **Main target:** reach a diamond pickaxe from an empty inventory on easy, in unseen seeds; survive 3 in-game days on normal; a 25-task test set.
  - **Stretch target:** defeat the **Ender Dragon** in an unknown world, in survival, without a prepared route. (Malde's run used a known seed, peaceful and a pre-verified portal.)
  - Companion behavior is measured with AFK tasks.
- **Two visibility modes:**
  - **Fair mode:** the default for evaluation and the report. The bot only knows blocks in its line of sight and blocks exposed to air, and writes what it has seen into memory.
  - **Full-knowledge mode:** selectable for AFK efficiency (Mineflayer otherwise knows every block in loaded chunks, i.e. "x-ray").
  - The mode is written into every run's result file; the "plays perfectly" claim is measured in fair mode.
- **Targets accepted (2026-10-15).** Every success rate is reported with a confidence interval: for example, the 95% Wilson interval of 8/10 is [49%, 94%] and of 4/5 is [38%, 96%]. Small-sample targets alone are therefore not proof of the claim; the protocol in §11.1 applies.

| Target | Measure | Value |
|---|---|---|
| Tech tree (main) | Empty inventory, **easy**, **fair mode**, 10 unseen test seeds, reach a diamond pickaxe | ≥ 8/10 seeds, ≤ 60 iterations |
| Ender Dragon (stretch) | Unknown world, survival, fair mode, no prepared route/portal/sensor | At least 1 verified run; time and LLM calls reported |
| Task set | ~25 tasks in 4 tiers (wood → stone → iron → diamond/armor/food/mobs) | ≥ 90% success (with the learned library) |
| Survival | 3 in-game days on normal (including nights) | ≤ 1 death |
| Reaction time | Emergency: event → action (L0) / tactical decision end to end (L1) | ≤ 100 ms / p95 ≤ 500 ms (§6.1) |
| Memory | §7.6 memory tasks; wasted trips (to exhausted/vanished targets) | ≥ 90% on tasks; wasted trips ≈ 0 |
| L2 routing | Sonnet alone vs cascade vs Opus (S5) | The chosen setup is justified by data |
| AFK pipeline | A 2-hour conditional task like §9.1, unattended | ≥ 90% completion, 0 deaths, 0 damage to player builds |
| Skill speed-up | §8.4: from scratch / core / core + library | LLM calls per hour fall (slope ± CI); time to diamond clearly shorter |
| Autonomy | `full` mode | Wrong assumptions, later corrections and irreversible actions reported; other modes: question, answer and timeout rates |
| L1 quality | Every L1 decision point vs its L0 rule | A point that does not beat the rule statistically goes back to L0 |
| Skills from recordings | 5 different demonstrations (table + furnace, wheat farm, 3×3 shelter, …) | ≥ 4/5 replayed successfully in fresh worlds |
| Cost | Total model cost to a diamond pickaxe | Reported; target < $5 per run |

**Ablations:** first the **single main hypothesis**: the contribution of the learned library. Then, in order: L1 (rule vs Jev; the "no L1" arm keeps the L0 safety reflexes **on**), memory (off / structured only / structured + RAG), L2 (Sonnet alone vs cascade vs Opus). A "Claude vs local L2" arm is dropped: the MindForge finding already predicts its outcome.

### 11.1 Evaluation protocol

- **Pre-registration:** the task set, seeds and success predicates are frozen before evaluation starts. Prompt tuning happens only on development seeds.
- **Learning and testing are separate:** learning seeds ≠ test seeds; the library is frozen during testing. Online learning is measured as a separate experiment.
- **Given vs learned:** the hand-written core (including `obtain`) and learned skills are reported separately. Main claim: "the learned library reduces time and L2 calls in **unseen** worlds without lowering success".
- **Paired comparisons:** ≥ 20–30 paired runs (same seed + task + start state) in the main arms. McNemar tests and bootstrap confidence intervals; seed/task clustering is taken into account. Sample sizes come from pilot variance and the smallest meaningful difference.
- **Mostly short scenarios:** long runs (diamond, 3 days) are few; the weight is on 2–10 minute scenario tasks set up over RCON. A **wall-clock budget** table is kept (time per run, $, number of parallel servers; several Docker servers on the PC).
- **Additional metrics:** wall-clock time, $ per success, L2 p95, deaths/hour, damage, time without progress, p95/p99 reaction, **false-success rate**, crash/disconnect rate and unattended run time, skill reuse rate, never-used skill rate.
- **Failures are kept:** timeouts, disconnects and verifier uncertainty are never removed from the report.
- **L1 data:** consecutive states are not independent samples. Miss rate on rare dangers, false alarms and abstentions are measured separately.
- **Skills from recordings:** the unit is "demonstration × N fresh-world replays"; success rate per demonstration ± confidence interval.

---

## 12. Roadmap

The week-by-week schedule, work items, PR breakdown and review guide are in **[`plan.md`](plan.md)** (delivery: 2026-11-19).

**Scope decision (2026-10-15):** everything in the vision stays in scope. The reviewers' schedule warning is managed by **ordering**: first the core that works end to end and can measure the main claim, then extensions in priority order. After every milestone the main-claim measurement is updated, so whenever delivery day comes there is a reportable result.

| Milestone | Content | Done when |
|---|---|---|
| **Spikes S1–S7** | §14.6 experiments (S8 Doom comes with the Doom plugin) | Each spike has a written decision (continue / change / drop) |
| **M0 Infrastructure** | Python core skeleton (uv) + TypeScript Minecraft plugin skeleton, CI (lint/types/tests), Docker MC 1.21.11 (RCON on, bot not op), bot connects, viewer | The bot spawns and can be watched in the browser |
| **M1 Plugin core** | Thin protocol, separate process + watchdog + primitive broker, cancellable primitives, action arbiter, L0 safety reflexes, independent predicates, reset, visibility filter | A hand-written skill goes from wood to a crafting table; interrupt/disconnect tests pass |
| **M2 Single-task loop + evaluation skeleton** | L2 code writer (TypeScript + `tsc`), predicate-first, 4 attempts, telemetry + trace ids; **evaluation runner** and the first 5 frozen scenarios | "Craft a wooden pickaxe" from scratch; the runner produces a report |
| **M3 Skill library** | Contracts, draft → verified (+ candidate versions), scenario tests, bounded `obtain`, starter core | A learned skill is used in an unseen seed (S7 criterion) |
| **M4 Curriculum + structured memory** | Proposals + feasibility + failure lessons; places, chests, resource state (`world_instance_id`) | 60 iterations of exploration; "go back to the village", "which chest has the diamonds" pass |
| **M5 L1** | `DecisionClient` (rules + Jev + 1 local), question registry, shadow mode, event-driven tactics | Points that pass the value test are active, the rest stay in L0 |
| **M6 Commands / AFK** | `#command` parser, L2 → Task IR, triggers + guards + budgets, persistent state, AFK summary | The §9.1 example finishes unattended |
| **M7 Record a skill v1** | Proxy recording, meaning layers, blueprint + subgoal macro, `//` text narration, independent acceptance predicate | A demonstrated shelter is rebuilt on unseen terrain |
| **M7b Record a skill v2** | Behavioral skills (farming, combat) via L2, verified on unseen terrain, voice narration (Whisper) | A demonstrated farm/tactic is repeated on different terrain |
| **M8 Evaluation + report** | §11.1 protocol, main hypothesis + ordered ablations | The §11 table is filled with confidence intervals |
| **M9 Demo + delivery** | Dashboard, README, a fixed "filming seed", diary + highlights, video, presentation | The delivery package is ready |
| **M10 Extensions** (in scope, in order) | `approver`/`consult`; voice commands + TTS; personality narration + diary; episodic RAG + lessons; visual pipeline editor + scheduling; L3 (S1-Bench, Unsloth fine-tune, counterfactual pilot); Ender Dragon stretch target | Each by its own criterion (§8–§10) |
| **M11 Second game: Doom** (after delivery) | ViZDoom plugin (Python) on the same core; then retro and pixel plugins | Contract generality metrics (§5.5) |
| **M12 Multi-agent** (after delivery) | Per-agent identities, shared/private memory, world coordinator, structured messages (§5.5) | Two bots split a task without competing for the same resource |

## 13. Risks

| Risk | Mitigation |
|---|---|
| Scope: the whole vision stays in scope; both reviewers named this the biggest risk | Ordering: first the core that measures the main claim (M0–M5), with the measurement updated at every milestone; extensions (M7b, M10) after. There is always a reportable result |
| LLM code locks the event loop or reaches secrets | Separate restricted executor, primitive broker, external watchdog, static rules (§5.2) |
| The bot "x-rays" loaded chunks and evaluation becomes unfairly easy | Fair visibility mode for evaluation (§11); bot not op; `/` commands forbidden |
| Stale plugins (pathfinder 2023, pvp 2022, viewer falls back to 1.21.4 assets) | Spike S1; Mindcraft's patches; budget for a fork/patch |
| Jev service outage / a model version changes behavior | `DecisionClient` + local providers; versioned question definitions; S1-Bench rerun on model changes |
| Stale memory (mine exhausted, village destroyed) → wrong decisions | Validity intervals, re-verification when passing nearby, newer observation wins |
| L2 silently makes mistakes | Objective checks (`tsc`, predicates, feasibility); the verifier measures every result; escalation logs reviewed |
| Personality breaks work (gets scared and drops the task, delays a player command) | Mood effects bounded in code; player commands always first; off in work mode |
| An unattended AFK pipeline does damage (breaks builds, gets lost, dies) | Guards (radius, protected builds), budgets, triggers, persistent state + death recovery, regular reports |
| An autonomous bot does something irreversible on a wrong reading | Pre-set policies (forbidden actions, protected areas), preference for reversible options, higher threshold for irreversible actions, decision log |
| The plugin contract is shaped by Minecraft and does not fit other games | Versioned contract; early ViZDoom spike (S8); no game names in the core |
| Prompt injection through chat, signs or books | In-game text is marked as state data, never instructions |
| A fine-tuned model overfits the game distribution | Split without seed/scenario leakage, calibration holdout, in-game A/B |
| L1 model errors (counting, distances, option order) | Numeric work in code; option-shuffle tests; below threshold, fall back to the rule |
| Weak generalization from recordings to skills | Hierarchical segmentation + narration + verification on unseen terrain + repair loop |
| Mineflayer version mismatch / skill drift | Pinned MC version, lockfiles, regression runs |
| LLM-written code runs on the local machine | Isolation, local offline server only, never connect to a public server |
| Randomness → irreproducible results | Fixed seeds, hard resets, repeated runs, `world_instance_id` |

---

## 14. External review: Claude Opus 5.5 + GPT-6-Astra (2026-10-15)

Two independent reviewers read all documents with the same instructions and wrote harsh critiques:
- **Claude Opus 5.5:** a sub-agent with web verification.
- **GPT-6-Astra:** through the Codex CLI, high reasoning effort, read-only.

Raw reports: [reviews/2026-10-15-opus.md](reviews/2026-10-15-opus.md), [reviews/2026-10-15-astra.md](reviews/2026-10-15-astra.md).

### 14.1 Shared verdict

> Both reached the same conclusion: **the research is strong, but the design is too big for a course delivery; the biggest risk is that the end-to-end slice showing the contribution of learning comes too late.** Judged right: deterministic verification, "location questions are code, not RAG", the value test against L0, the game-plugin boundary.

### 14.2 Problems both found (high confidence) and the fixes applied

| # | Problem | Fix (applied in this document) |
|---|---|---|
| 1 | **Wrong sandbox model.** `node:vm`'s timeout does not cover async code; a synchronous LLM-written loop locks the event loop (physics, keepalive, monitor all stop). A local server does not protect the developer's machine or API keys. | Skill execution **always in a separate process**: no keys, restricted file/network access, resource limits; an external watchdog kills and reconnects on a hang. The in-process plugin path was removed. Primitives go through a permission-checked broker with cancellation checks. Static rule: no loop without `await` (§5.2, decision 8). |
| 2 | **The danger monitor was in the wrong layer.** Danger is a numeric decision and Jev is weak with numbers; with one request in flight, 300 ms latency allows at most ~3.3 Hz, so 5 Hz is impossible. In Malde's run Jev ran at ~0.25 Hz, event-driven. | **Emergency reaction in L0** (rule + timer + pvp; event → action ≤100 ms). L1 does **event-driven tactical choice** and language-semantic decisions. New L1 points start in **shadow mode** (§6.1, §6.2, §6.4). |
| 3 | **Nobody owns the bot.** Skills, the monitor and triggers all drive movement and inventory (night + low health + full inventory = three competing "go home"s). `AbortSignal` is cooperative; pathfinder's `stop()` waits for the next node. | **Single action owner (arbiter):** explicit priorities, resource ownership, interrupt acknowledgement, late results of interrupted work discarded, preconditions re-checked before resuming (§6.4). |
| 4 | **A skill writes its own exam.** Code, intent card and success predicate come from the same induction; a misunderstood intent also yields a "successful" predicate. | **Independent verification:** the success predicate is written **before** and separately from the code (predicate-first synthesis) and frozen; the verifier is tested on negative examples; undecidable results are `unknown`, never success (§8.2, §8.3). |
| 5 | **The contribution of learning cannot be measured.** `obtain` + starter skills solve much of the tech tree in code; learning and testing on the same seeds (leakage). | **Evaluation protocol** (§11.1): separate learning and test seeds, frozen test set and library, hand-written and learned skills reported separately. Main claim: "the learned library reduces time and L2 calls in **unseen** worlds without lowering success". |
| 6 | **No statistical power.** The 95% Wilson interval of 8/10 is [49–94%], of 4/5 [38–96%]; 3 repeats cannot separate arms. | ≥ 20–30 **paired** runs in the main arms, McNemar / bootstrap CIs; fewer ablations, more repeats; pre-registration (§11.1). |
| 7 | **A seed is not a world identity.** Two worlds from the same seed diverge; old chest/mine memory leaks across resets. | Memory key `world_instance_id + episode_id + reset generation`; seed is metadata only (§7.5). |
| 8 | **Counterfactual labeling is noisy.** Minecraft is not deterministic; a "damage within 3 s" label depends on the chosen action (a correct escape labels a dangerous state "safe"). | Counterfactuals only as a **pilot on one decision point**; danger label and policy outcome kept apart; repeated rollouts as distributions; rule oracles first (§6.7). |
| 9 | **API compatibility is not behavioral compatibility.** Providers' confidence values are not comparable (Unsloth also says thresholds do not transfer). The claim "Unsloth is Jev-compatible, only the address changes" could not be verified. | Thresholds per `(question, provider, model version, projection)`; agreement is not correctness, shared errors are measured; the Unsloth claim is marked "not verified" (§6.3, §6.5). |
| 10 | **The plugin contract is derived from one game and too wide;** "core change ≈ 0" is the wrong metric (an overly generic JSON interface also gives zero) and cannot be measured at delivery. | **Thin mandatory core** (`handshake, observe, act, runSkill, interrupt, reset, events`) + optional capabilities. Generality metrics: plugin development time, duplicated code, escape hatches, behavioral parity. Tested with a ViZDoom spike (S8), not on paper (§5.2, §5.5). |
| 11 | **An `approver` timeout expanded permission.** A user who chose "ask me first" could lose valuables because they did not answer in time. | A timeout **never grants permission**: the risky step is skipped, an alternative is chosen, or the task ends safely (§5.6). |
| 12 | **Document errors:** leftover table in the autonomy section; MineCollab "drops to 15%" (actually "a drop of as much as 15%"); SIMA 2's 31%→65% is not Minecraft-specific; "Work2Skill does not test skills" was wrong; in Blocks.ai **engine data** selects the phase; inconsistent L1 latency budgets; Signed Rescue Routing results still "TBD"; roadmap order wrong (AFK before cancellable primitives). | All fixed. One latency budget is defined in §6.1. |

**Additional findings from Astra (verified):**
- **Malde's repository** is [rmalde/minecraft-agent](https://github.com/rmalde/minecraft-agent): the End portal is pre-verified, a village and obsidian chests are ready in the seed, and the dragon head position is read by a read-only server **sensor**. It shows integration, not learning or a causal contribution of L1 (§2.5).
- **Claude has an official help page** for recording: Mac Cowork only, ~10 minutes, video/audio not kept, screenshots retained. The official page does **not** describe follow-up questions (§4.1).

**Additional findings from Opus:**
- **Perception fairness ("x-ray"):** Mineflayer sees all loaded chunks, including diamonds inside stone; LLM code could call `bot.chat('/give …')`. → The bot is not op, scenario setup is **RCON only**, `/` commands are statically forbidden in LLM code, and evaluation uses fair visibility (§11).
- **Stale plugins:** `mineflayer-pathfinder` 2.4.5 (2023-09), `mineflayer-pvp` 1.3.2 (2022-07), `mineflayer-tool` 1.2.0 (2022-05); `prismarine-viewer` falls back to 1.21.4 assets on 1.21.11. → The first spike is a compatibility test (S1).
- **Recording-proxy difficulties:** the 1.20.2+ configuration phase, signed chat (`enforce-secure-profile=false`), two crafting paths (recipe-book packet and slot clicks), and divergence between client requests and server acknowledgements.
- **Wall-clock budget:** 6 ablations × 10 seeds × 3 repeats ≈ 180–360 hours. Keep long runs few; weight 2–10 minute RCON scenario tasks.

### 14.3 Gaps (union of both reviews) → added to the design

| Gap | Direction |
|---|---|
| State consistency | Snapshot versions, event sequence numbers, filling gaps in the stream, `unknown` fields |
| Restart reconciliation | Actions known to be sent but not known to be applied; idempotency against duplicate effects |
| Authority separation | The evaluator's `/give`, reset and ground-truth access are closed to the agent (RCON only for the evaluator and scenario builder) |
| Observability | One trace id (L2 call → skill → primitive → event), queue time, discarded stale answers, interrupt latency, verifier disagreement, session replay |
| Test infrastructure | A fake bot (primitive unit tests), a Docker MC scenario runner, a deterministic test world |
| Data lifecycle | Atomic publishing of SQLite rows and `.ts` files, skill dependency hashes, migrations, log retention and compression |
| Version matrix | Skill ↔ primitive API ↔ prompt ↔ model ↔ MC version (the practical side of skill drift) |
| Security | Nothing sensitive in the executor (`require`, `process`, network, `.env`). Chat, sign and book text is a **prompt-injection channel** → marked as state data, never instructions |
| Operations | API outages, the PC sleeping/off (fallback path), GPU memory pressure, training vs serving contention, disk limits |
| Course mapping | "≥20 tests, success, cost, latency, video" mapped to milestones; a fixed "filming seed" for the demo |
| Observation actions | "I don't know" → opening a chest or inspecting an area is a legitimate action; uncertainty does not turn into an automatic guess (Astra) |
| Limits of `obtain` | A finite supported item set, cycle detection, resource reservation, explicit `unsupported` / `unreachable` (Astra) |
| Meaning layers in recording | Request / server ack / observed change / inferred meaning kept apart; raw recording kept; L1 cleaning is reversible marking (Astra) |

### 14.4 Questions the reviewers raised → decisions (2026-10-15)

| Topic | Decision |
|---|---|
| L2 routing | **Sonnet 5.5 by default**, Haiku 5.5 for text; cascade and Opus measured in S5 (§6.8) |
| Delivery scope | **Everything stays in scope**; the risk is managed by ordering (§12) |
| Main claim | **Learning by playing** (§11) |
| Definition of "perfect" | **Tiered**: diamond + 3-day survival + 25 tasks as the main target; Ender Dragon in an unknown world as the stretch target (§11) |
| Perception fairness | **Two modes**: fair (evaluation) + full knowledge (AFK option) (§11) |
| Recording order | **Phased**: v1 blueprint + macro, v2 behavioral (§4.6) |
| Mindcraft | **Borrow parts**, do not build on top (§5.4) |
| Targets | **Accepted** as in §11 |
| Second game | **Doom**, after delivery |
| Core language | **Python** (Minecraft plugin in TypeScript) |
| Multi-agent | **Future extension** (§5.5, M12) |

The reviewers' original positions, for the record: both asked for the cascade to be proven against Sonnet alone; both recommended postponing personality/mood, voice, the visual editor, most L1 providers, fine-tuning and episodic RAG; both asked for one main claim and a finite definition of "perfect"; Opus raised the visibility question and suggested building on Mindcraft; Astra suggested starting recording with one skill family.

### 14.5 Alternative ideas adopted into the design

1. **Predicate-first skill synthesis:** first the predicate and scenario, then the code (14.2 #4).
2. **Skills in TypeScript with `tsc` type checking:** invented primitives and wrong arguments are caught at compile time; also the cheapest objective escalation trigger (Opus).
3. **A bounded skill language first:** the Task IR / behavior tree as the skill format; free code only in leaves the DSL cannot express. Shrinks sandbox, interrupt and resume problems (both).
4. **Shadow-mode L1** (Astra) + an **offline decision benchmark**: `(state, decision, outcome)` tuples from logs; providers compared without running the game (Opus).
5. **Candidate skill versions:** a repair never overwrites a working skill; the candidate must pass regression first (Astra).
6. **Teaching by correction (DAgger style):** the bot tries, the player corrects with `//` ("no, place the torch first"); the correction becomes a rule. Cheaper than generalizing from one demonstration (Opus).
7. **Learning the difference from a demonstration:** instead of rediscovering existing primitives, extract the **new** order, conditions and exceptions in the demonstration (Astra).
8. **Counterexample factory:** automatically generate states that would break a skill (missing tool, obstacle, changed target) (Astra).
9. **`/tick freeze` / `/tick step`** frozen scenarios: measure decision quality separately from latency (check compatibility with Mineflayer physics first) (Opus).
10. **A night shift (L3) via the Batch API:** descriptions, regression repair proposals and teacher labels in bulk at a 50% discount (Opus).

### 14.6 First experiments of the coding phase

Run **before or alongside M0–M1**; each tests the riskiest assumption as cheaply as possible:

| # | Hypothesis | Experiment | Success criterion | Time box |
|---|---|---|---|---|
| S1 | MC 1.21.11 + mineflayer 4.39 + pathfinder/collectblock/pvp/tool + viewer work unpatched (or with Mindcraft's patches) | Docker itzg; the bot walks 100 blocks, chops a tree, crafts a table and pickaxe, kills a zombie, uses a chest; 10 runs | 10/10 without errors; the viewer shows 1.21.11 blocks. Otherwise a version/fork/patch decision | 1 day |
| S2 | A separate process + watchdog kills bad code within 2 s and stale work cannot send actions | 20 faulty skills (sync loop, `await`ed infinite loop, unhandled rejection, 5-minute pathfind, `process.exit`); `vm` vs separate process; interrupts and disconnects mid-action | 100% kills ≤2 s in the separate-process arm; the main process survives; stale work sends nothing after the ack | 2 days |
| S3 | The verifier is independent and resets are reproducible | Correct/incorrect final states for 3 tasks + 20 resets | Zero false successes on negatives; defined start-state fields match | 1.5 days |
| S4 | Jev beats the L0 rule meaningfully on a contextual decision with p95 ≤300 ms | 200 RCON scenarios; rule vs Jev vs Haiku (+1 local); 2 shuffled queries; label and policy outcome separate | Jev ≥ rule + 5 points (McNemar p < 0.05) **and** p95 ≤300 ms; otherwise L1 stays on language-semantic points | 3 days |
| S5 | The cascade or Opus adds value over Sonnet alone for code | 10-task vertical slice (wood → stone pickaxe → furnace → iron); Haiku / Sonnet / Opus alone + cascade, 5 repeats; attempts, wall clock, $ | Cascade not clearly worse on success **and** clearly better on time or $; otherwise Sonnet stays default | 3 days |
| S6 | A vanilla client plays stably through the proxy and events are extracted correctly | 10 minutes of play; break/place/craft/`//` events cross-checked against the server-side block diff; a 3×3 shelter blueprint rebuilt in a fresh world | No disconnects; ≥95% of events correct; blueprint ≥95% block accuracy in 5/5 replays | 2–3 days |
| S7 | One learned composite skill gives a gain in unseen worlds | Frozen core vs core + learned skill; separate test seeds | Time and L2 calls fall without lower success; the skill is actually called | 2 days |
| S8 | The plugin contract fits a second game (with the Doom plugin) | ViZDoom (Python) with only `handshake/observe/act/reset` | Works in 1 day; a list of needed contract changes | 1 day |

---

## Sources

**Minecraft agents:** [Voyager paper](https://arxiv.org/abs/2305.16291) · [Voyager repo](https://github.com/MineDojo/Voyager) · [Mindcraft](https://github.com/mindcraft-bots/mindcraft) · [MineCollab](https://arxiv.org/abs/2504.17950) · [ODYSSEY](https://arxiv.org/abs/2407.15325) · [MindForge](https://arxiv.org/abs/2411.12977) · [MineEvolve](https://arxiv.org/abs/2603.13131) · [Programmatic Skill Networks](https://arxiv.org/abs/2601.03509) · [Project Sid](https://arxiv.org/abs/2411.00114) · [GITM](https://arxiv.org/abs/2305.17144) · [JARVIS-1](https://arxiv.org/abs/2311.05997) · [Optimus-1](https://arxiv.org/abs/2408.03615) · [MineNPC-Task](https://arxiv.org/abs/2601.05215) · [MineExplorer](https://arxiv.org/abs/2605.30931) · [PillagerBench](https://arxiv.org/abs/2509.06235) · [minecraft-mcp-server](https://github.com/yuniko-software/minecraft-mcp-server) · [Player2NPC](https://modrinth.com/mod/player2npc) · [Mineflayer](https://github.com/PrismarineJS/mineflayer) · [node-minecraft-protocol](https://github.com/PrismarineJS/node-minecraft-protocol)

**Skill libraries:** [Skill drift](https://arxiv.org/abs/2605.10990) · [SkillsBench](https://arxiv.org/abs/2602.12670) · [Skills in the wild](https://arxiv.org/abs/2604.04323) · [Generative skill composition](https://arxiv.org/abs/2606.32025) · [AgentSkillOS](https://arxiv.org/abs/2603.02176) · [SkillEval](https://arxiv.org/abs/2608.06891) · [NVIDIA SkillEvaluator](https://developer.nvidia.com/blog/evaluating-ai-agent-skill-performance-with-nvidia-skillevaluator/) · [SoK: Agentic Skills](https://arxiv.org/html/2602.20867)

**Jev / System One:** [The Register](https://www.theregister.com/ai-and-ml/2026/09/16/typesafe-ai-debuts-model-for-machines-that-plays-doom/5296711) · [DataCamp](https://www.datacamp.com/blog/system-one-models-jev) · [LumaDock](https://lumadock.com/blog/what-is-jev-typesafe) · [Medium](https://medium.com/@creativeaininja/typesafes-jev-makes-ai-decisions-fast-enough-to-play-doom-68fdcce1159a) · [jev-plays-doom](https://github.com/tirukovelamanoj/jev-plays-doom) · [Blocks.ai replica](https://blocks.ai/blog/jev-open-model-doom) · [TypeSafe docs](https://docs.typesafe.ai/llms.txt) · [models](https://docs.typesafe.ai/models.md) · [jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md) · [images](https://docs.typesafe.ai/images.md) · [skill suggestion](https://docs.typesafe.ai/cookbooks/skill_suggestion.md) · [self-consistency](https://docs.typesafe.ai/cookbooks/consistency_choice_cookbook.md) · [confidence routing](https://docs.typesafe.ai/patterns/confidence-routing.md) · [rmalde/minecraft-agent](https://github.com/rmalde/minecraft-agent) · [ASCII.jp on the Ender Dragon run](https://ascii.jp/en/elem/000/004/436/4436545/)

**Local decision models:** [Unsloth decision models](https://unsloth.ai/docs/new/train-your-own-decision-model-with-unsloth) · [Unsloth Laya serving](https://unsloth.ai/docs/models/decision-laya) · [AlphaSignal summary](https://alphasignal.ai/news/unsloth-turns-a-0-8b-model-into-a-fast-decision-engine-at-78-accuracy) · [GLiClass](https://arxiv.org/abs/2508.07662) · [BTZSC](https://arxiv.org/abs/2603.11991) · [Encoder vs LLM cost](https://arxiv.org/abs/2602.06370) · [LLM vs fine-tuned NLU](https://arxiv.org/abs/2608.20371) · [Agent distillation](https://arxiv.org/abs/2505.17612)

**General game agents:** [SIMA 2](https://arxiv.org/abs/2512.04797) · [Cradle](https://arxiv.org/abs/2403.03186) · [Lumine](https://arxiv.org/abs/2511.08892) · [NitroGen](https://arxiv.org/abs/2601.02427) · [Game-TARS](https://arxiv.org/abs/2510.23691) · [SpeedrunBench](https://arxiv.org/abs/2610.08076) · [Vals CUA-Bench summary](https://hermes-ai.net/news/vals-ai-s-cua-bench-humbles-every-frontier-agent-below-20-points/) · [AI for Games survey](https://arxiv.org/abs/2609.16679) · [LLM game agent survey](https://github.com/git-disl/awesome-LLM-game-agent-papers) · [General Modular Harness](https://arxiv.org/abs/2507.11633)

**Record a skill:** [Claude help center](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills) · [Claude: leadwithai](https://www.leadwithai.co/article/record-a-skill-claude-cowork) · [Claude: The Decoder](https://the-decoder.com/claude-cowork-learns-new-skills-through-screen-recordings-and-voice-over-explanations/) · [Claude: AI Weekly](https://aiweekly.co/alerts/anthropic-ships-record-a-skill-in-claude-cowork-desktop-app) · [Claude: remio critique](https://www.remio.ai/post/claude-cowork-skill-recording-turns-demonstrations-into-reusable-workflows-but-t) · [Claude: digitalapplied](https://www.digitalapplied.com/blog/claude-record-a-skill-train-agents-by-demonstration-2026) · [Codex Record & Replay docs](https://learn.chatgpt.com/docs/extend/record-and-replay) · [Codex hands-on](https://azukiazusa.dev/en/blog/workflow-to-reusable-skill/) · [Codex audit checklist](https://chatgptaihub.com/audit-repair-codex-record-replay-skill) · [kingy.ai](https://kingy.ai/news/codex-record-and-replay/) · [webiano](https://webiano.digital/record-and-replay-turns-a-single-demo-into-a-reusable-codex-skill/) · [Microsoft Skill Recorder](https://themenonlab.blog/blog/microsoft-skill-recorder-teach-agents-by-demonstration) · [Work2Skill](https://arxiv.org/abs/2610.12984) · [Hierarchical demonstrations](https://arxiv.org/abs/2606.20978) · [Skill-Pro](https://arxiv.org/abs/2602.01869)

**Memory and routing:** [MrSteve](https://arxiv.org/abs/2411.06736) · [EmbodiedMemory-Bench](https://arxiv.org/abs/2609.28236) · [Remember the Decision](https://arxiv.org/abs/2605.10870) · [Agent memory survey](https://arxiv.org/abs/2603.07670) · [Mindcraft memory prompt](https://huggingface.co/Sweaterdog/Andy-3.5/commit/fa0af5152a96579ab40fe5d8900a7d7a26f2ab62) · [Signed Rescue Routing](https://arxiv.org/abs/2609.07786) · [Cascade routing, ICML 2025](https://icml.cc/virtual/2025/poster/46183) · [Routing/cascading survey](https://arxiv.org/abs/2603.04445)

**Commands, pipelines and personality:** [Baritone](https://git.psf.lt/0xf8/baritone/raw/branch/1.12.2/USAGE.md) · [AIBot Bob](https://p.codekk.com/detail/6a033e245b02fc5c75bba05c) · [nekostulAICompanion](https://moddex.gg/mod/nekostulaicompanion) · [LLM → behavior trees](https://arxiv.org/abs/2302.12927) · [Wingman AI](https://ai.google.dev/competition/projects/wingman-ai) · [GPT-6 Astra: Dexerto](https://www.dexerto.com/minecraft/gpt-6-astra-forced-to-play-minecraft-gets-depressed-by-creeper-and-farms-potatoes-for-hours-3409634/) · [Tom's Hardware](https://www.tomshardware.com/tech-industry/artificial-intelligence/defeated-gpt-6-astra-model-spent-several-hours-just-farming-potatoes-after-being-blown-up-by-a-creeper-in-minecraft-openai-offering-gets-further-than-any-other-ai-system-in-141-hour-test) · [XDA](https://www.xda-developers.com/gpt-6-astra-made-amazing-progress-on-minecraft-until-a-creeper-blew-up-its-chest-and-it-spiralled-into-sadness/) · [Yahoo](https://www.yahoo.com/entertainment/articles/gpt-6-astra-plays-minecraft-224156819.html) · [Project Sid: MIT TR](https://www.technologyreview.com/2024/11/27/1107377/a-minecraft-town-of-ai-characters-made-friends-invented-jobs-and-spread-religion/amp/) · [MIMIC](https://arxiv.org/html/2510.01635v1)

**Autonomy and architecture:** [Levels of Autonomy for AI Agents](https://arxiv.org/abs/2506.12469) · [Knight Columbia summary](https://knightcolumbia.org/content/levels-of-autonomy-for-ai-agents-1) · [Human out of the loop](https://concepts.dsebastien.net/concept/human-out-of-the-loop/) · [HF: against fully autonomous agents](https://aiweekly.co/node/9510) · [IEEE Spectrum: approval processes](https://spectrum.ieee.org/agentic-ai-humans-in-loop) · [Node vm timeouts](https://nodejs.org/docs/latest-v22.x/api/vm.html#timeout-interactions-with-asynchronous-tasks-and-promises) · [mineflayer-pathfinder stop](https://github.com/PrismarineJS/mineflayer-pathfinder#botpathfinderstop)
