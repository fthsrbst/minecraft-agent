"""The agent runtime with a fake bot and a scripted router LLM."""

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from agent_core.agent import AgentRuntime, Autonomy
from agent_core.commands import Vocabulary
from agent_core.intent import parse_intent
from agent_core.llm import BackendResult, LlmClient, LlmRequest, Usage
from agent_core.memory.places import PlaceStore
from agent_core.plugins import JsonObject
from agent_core.skills import SkillResult
from agent_core.telemetry import TelemetryRecorder

VOCABULARY = Vocabulary.from_handshake(
    {
        "prefix": "#",
        "commands": [
            {
                "name": "goto",
                "usage": "#goto <place>",
                "description": "go",
                "args": [{"name": "target", "type": "position"}],
                "code": "GOTO",
            },
            {
                "name": "stop",
                "usage": "#stop",
                "description": "stop",
                "args": [],
                "builtin": "stop",
            },
            {
                "name": "sethome",
                "usage": "#sethome [name]",
                "description": "save",
                "args": [{"name": "name", "type": "word", "default": "home"}],
                "builtin": "remember-place",
            },
            {
                "name": "places",
                "usage": "#places",
                "description": "list",
                "args": [],
                "builtin": "list-places",
            },
        ],
    }
)


@dataclass
class FakeBot:
    said: list[str] = field(default_factory=list[str])
    skills: list[tuple[str, JsonObject]] = field(default_factory=list[tuple[str, JsonObject]])
    interrupts: int = 0
    skill_seconds: float = 0.0

    async def chat(self, text: str) -> None:
        self.said.append(text)

    async def observe(self) -> JsonObject:
        return {"position": {"x": 10.4, "y": 64.0, "z": -7.6}, "dimension": "overworld"}

    async def run_skill(self, code: str, args: JsonObject, timeout_s: float) -> SkillResult:
        self.skills.append((code, args))
        await asyncio.sleep(self.skill_seconds)
        return SkillResult("r", "ok", None, None, 1.0, 1, ())

    async def interrupt(self) -> None:
        self.interrupts += 1


@dataclass
class Router:
    answers: list[str]
    provider: str = "scripted"

    async def create(self, request: LlmRequest) -> BackendResult:
        return BackendResult(self.answers.pop(0), request.model, "end_turn", Usage(1, 1))


def intent(kind: str, text: str) -> str:
    return f"<intent>{json.dumps({'kind': kind, 'text': text})}</intent>"


def make(
    tmp_path: Path,
    answers: list[str],
    autonomy: Autonomy = Autonomy.FULL,
    skill_seconds: float = 0.0,
) -> tuple[AgentRuntime, FakeBot, list[str]]:
    bot = FakeBot(skill_seconds=skill_seconds)
    goals: list[str] = []

    async def run_task(goal: str) -> str:
        goals.append(goal)
        return f"Done: {goal}"

    runtime = AgentRuntime(
        bot,
        "AgentBot",
        VOCABULARY,
        PlaceStore(tmp_path / "p.sqlite"),
        "seed1",
        LlmClient(Router(answers), TelemetryRecorder(tmp_path / "t.jsonl")),
        autonomy,
        run_task,
        ask_timeout_s=0.2,
    )
    return runtime, bot, goals


async def settle(runtime: AgentRuntime) -> None:
    if runtime._work is not None:  # pyright: ignore[reportPrivateUsage]
        await runtime._work  # pyright: ignore[reportPrivateUsage]


def test_sethome_then_goto_home(tmp_path: Path) -> None:
    runtime, bot, _ = make(tmp_path, [])

    async def main() -> None:
        await runtime.on_chat("Fatih", "#sethome")
        await runtime.on_chat("Fatih", "#goto home")
        await settle(runtime)
        await runtime.on_chat("Fatih", "#places")

    asyncio.run(main())
    assert bot.said[0] == "Saved home at 10 64 -8."
    assert bot.skills == [("GOTO", {"target": {"x": 10.4, "y": 64.0, "z": -7.6}})]
    assert "Done: goto." in bot.said
    assert bot.said[-1] == "Places: home (10 64 -8)"


def test_stop_cancels_the_running_work(tmp_path: Path) -> None:
    runtime, bot, _ = make(tmp_path, [], skill_seconds=5)

    async def main() -> None:
        await runtime.on_chat("Fatih", "#goto 1 2 3")
        await asyncio.sleep(0.05)
        await runtime.on_chat("Fatih", "#stop")

    asyncio.run(main())
    assert bot.interrupts == 1
    assert bot.said[-1] == "Stopped."


def test_a_bad_command_is_explained_and_unaddressed_chat_is_ignored(tmp_path: Path) -> None:
    runtime, bot, _ = make(tmp_path, [])
    asyncio.run(runtime.on_chat("Fatih", "#goto nowhere"))
    asyncio.run(runtime.on_chat("Fatih", "nice weather today"))
    assert bot.said == ["no place called 'nowhere'; save one with #sethome nowhere"]


def test_free_text_reply_and_routed_command(tmp_path: Path) -> None:
    runtime, bot, _ = make(
        tmp_path, [intent("reply", "Hi Fatih!"), intent("command", "#sethome base")]
    )
    asyncio.run(runtime.on_chat("Fatih", "hello AgentBot"))
    asyncio.run(runtime.on_chat("Fatih", "AgentBot remember this spot as base"))
    assert bot.said == ["Hi Fatih!", "Saved base at 10 64 -8."]


def test_full_autonomy_never_asks(tmp_path: Path) -> None:
    runtime, bot, goals = make(tmp_path, [intent("task", "Craft a stone pickaxe")])

    async def main() -> None:
        await runtime.on_chat("Fatih", "AgentBot make me a stone pickaxe")
        await settle(runtime)

    asyncio.run(main())
    assert goals == ["Craft a stone pickaxe"]
    assert not any("?" in line for line in bot.said)


def test_consult_asks_and_no_answer_means_no(tmp_path: Path) -> None:
    runtime, bot, goals = make(tmp_path, [intent("task", "Dig a big hole")], Autonomy.CONSULT)
    asyncio.run(runtime.on_chat("Fatih", "AgentBot dig a big hole here"))
    assert goals == []
    assert bot.said[0].startswith("Should I: Dig a big hole?")
    assert bot.said[-1] == "No answer, so I will not do it."


def test_consult_proceeds_on_yes_and_keeps_listening_while_asking(tmp_path: Path) -> None:
    runtime, bot, goals = make(tmp_path, [intent("task", "Craft a chest")], Autonomy.CONSULT)
    runtime.ask_timeout_s = 2

    async def main() -> None:
        asking = asyncio.create_task(runtime.on_chat("Fatih", "AgentBot craft a chest"))
        await asyncio.sleep(0.05)
        await runtime.on_chat("Fatih", "#sethome")  # handled while the question is open
        await runtime.on_chat("Fatih", "yes")
        await asking
        await settle(runtime)

    asyncio.run(main())
    assert "Saved home at 10 64 -8." in bot.said
    assert goals == ["Craft a chest"]


def test_intent_parsing_refuses_server_commands() -> None:
    assert parse_intent(intent("reply", "hello\nthere"), "#").text == "hello there"
    for bad in (intent("reply", "/op Fatih"), intent("command", "goto home"), "no tags"):
        try:
            parse_intent(bad, "#")
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")
