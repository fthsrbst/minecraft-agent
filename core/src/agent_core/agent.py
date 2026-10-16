"""The agent runtime (plan P3.2/P3.3): chat in, work out.

Typed `#commands` run at once. Free text addressed to the bot goes to L2 (`intent.route`): a
command, a task for the Voyager loop, or a persona reply. One piece of work runs at a time; a new
one replaces it, `#stop` ends it. Places are remembered per world.

Autonomy (decision 9b): in `full` the bot never asks. In `consult` it asks before starting a task
it interpreted from free text; the question has a timeout, and no answer means no: a timeout never
grants permission. Asking never blocks the bot: other messages are handled meanwhile.

    uv run --env-file ../.env python -m agent_core.agent ../plugins/<game> [--autonomy full|consult]
"""

import argparse
import asyncio
import contextlib
import logging
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from agent_core.commands import CommandError, Invocation, Vocabulary, describe, parse_command
from agent_core.decisions.client import ChoiceProvider, DecisionClient
from agent_core.decisions.questions import command_route
from agent_core.decisions.rules import KeywordRule
from agent_core.decisions.typesafe_provider import JevProvider, TypeSafeError
from agent_core.intent import DEFAULT_PERSONA, intent_system_prompt, route
from agent_core.library import SkillLibrary
from agent_core.llm import LlmClient
from agent_core.llm.anthropic_backend import AnthropicBackend
from agent_core.memory.places import PlaceError, PlaceStore
from agent_core.plugins import JsonObject, JsonValue, ManifestError, PluginClient, PluginError
from agent_core.skills import SkillResult, run_skill
from agent_core.telemetry import TelemetryRecorder, new_trace_id
from agent_core.voyager.loop import PluginSession, VoyagerAgent
from agent_core.voyager.task import Task

_log = logging.getLogger(__name__)

COMMAND_TIMEOUT_S = 600.0
ASK_TIMEOUT_S = 30.0
MAX_CHAT = 240
RATE_S = 3.0
MAX_PARALLEL_LLM = 2
# L1 acts only on very confident model choices, and never for commands that overwrite memory.
L1_ACT_CONFIDENCE = 0.9
L1_NEVER = frozenset({"remember-place"})
YES = frozenset({"yes", "y", "ok", "okay", "sure", "do it", "go", "yes please", "evet"})
# Turkish answers too: "hay\\u0131r" is the Turkish "no" spelled with a dotless i.
NO = frozenset({"no", "n", "nope", "don't", "hayir", "hay\u0131r"})


class Autonomy(StrEnum):
    FULL = "full"
    CONSULT = "consult"


class BotPort(Protocol):
    async def chat(self, text: str) -> None: ...

    async def observe(self) -> JsonObject: ...

    async def run_skill(self, code: str, args: JsonObject, timeout_s: float) -> SkillResult: ...

    async def interrupt(self) -> None: ...


TaskRunner = Callable[[str], Awaitable[str]]


Origin = Literal["typed", "routed", "l1"]


@dataclass(slots=True)
class AgentRuntime:
    bot: BotPort
    name: str
    vocabulary: Vocabulary
    places: PlaceStore
    world: str
    llm: LlmClient
    autonomy: Autonomy
    run_task: TaskRunner  # runs a free-text goal (the Voyager loop) and describes the outcome
    persona: str = DEFAULT_PERSONA
    ask_timeout_s: float = ASK_TIMEOUT_S
    # L1 (P3.4): a fast choice of command, task or chat before L2. In shadow mode (default for a
    # new decision point, decision 10) it is only logged, in the background; with `l1_act` a
    # confident Jev choice of a command that needs no arguments runs at once, without L2.
    decisions: DecisionClient | None = None
    l1_act: bool = False
    # A player's addressed messages cost LLM calls: at most one per `rate_s` seconds each.
    rate_s: float = RATE_S
    _work: asyncio.Task[None] | None = field(default=None, init=False)
    _work_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _question: tuple[str, asyncio.Future[bool]] | None = field(default=None, init=False)
    _system: str = field(default="", init=False)
    _last_addressed: dict[str, float] = field(default_factory=dict[str, float], init=False)
    _llm_slots: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(MAX_PARALLEL_LLM), init=False
    )
    _shadow: set[asyncio.Task[object]] = field(
        default_factory=set[asyncio.Task[object]], init=False
    )

    def __post_init__(self) -> None:
        commands = describe(list(self.vocabulary.commands.values()))
        self._system = intent_system_prompt(
            self.name, self.persona, commands, self.vocabulary.prefix
        )

    async def on_chat(self, sender: str, message: str, origin: Origin = "typed") -> None:
        if sender == self.name:
            return
        if origin == "typed" and self._answer(sender, message):
            return
        try:
            invocation = parse_command(
                message, self.vocabulary, sender=sender, places=self._place_position
            )
        except CommandError as error:
            await self.say(str(error))
            return
        if invocation is not None:
            await self.command(invocation, sender, origin)
            return
        if origin != "typed" or not self._mentions_me(message):
            return  # not for us (or a routed line that is not a command: never loop)
        now = asyncio.get_running_loop().time()
        if now - self._last_addressed.get(sender, -1e9) < self.rate_s:
            return  # rate limit: also breaks reply loops between two bots
        self._last_addressed[sender] = now
        async with self._llm_slots:
            if await self._l1(sender, message):
                return
            intent = await route(
                self.llm, self._system, sender, message, self.vocabulary.prefix, new_trace_id()
            )
        if intent.kind == "reply":
            await self.say(intent.text)
        elif intent.kind == "command":
            await self.on_chat(sender, intent.text, origin="routed")
        else:
            await self.task(intent.text, sender)

    async def _l1(self, sender: str, message: str) -> bool:
        """True when L1 handled the message: act mode, a confident Jev choice, no arguments."""
        if self.decisions is None:
            return False
        decision_call = self.decisions.decide(
            command_route(self.vocabulary),
            {"message": message, "sender": sender},
            shadow=not self.l1_act,
        )
        if not self.l1_act:
            # Shadow mode logs only: it must not add L1 latency in front of L2.
            task: asyncio.Task[object] = asyncio.create_task(decision_call)
            self._shadow.add(task)
            task.add_done_callback(self._shadow.discard)
            return False
        decision = await decision_call
        spec = self.vocabulary.commands.get(decision.choice or "")
        # The keyword rule is a fallback and a baseline, never a reason to act: it cannot read
        # "wait, don't stop". Only a confident model choice acts.
        if not decision.accepted or decision.provider == "rules" or spec is None:
            return False
        if decision.confidence < L1_ACT_CONFIDENCE or spec.builtin in L1_NEVER:
            return False
        if any("default" not in arg for arg in spec.args):
            return False  # arguments must come from the message: L2 writes the command line
        await self.on_chat(sender, f"{self.vocabulary.prefix}{spec.name}", origin="l1")
        return True

    async def command(self, invocation: Invocation, sender: str, origin: Origin = "typed") -> None:
        spec = invocation.spec
        if spec.builtin == "stop":
            asking = self._question is not None
            if await self.stop():
                await self.say("Stopped.")
            elif not asking:  # a withdrawn question already says "Okay, I will not."
                await self.say("I was not doing anything.")
        elif spec.builtin == "remember-place":
            await self._remember(str(invocation.args.get("name", "home")), sender)
        elif spec.builtin == "list-places":
            places = self.places.all(self.world)
            listed = ", ".join(f"{p.name} ({p.x:.0f} {p.y:.0f} {p.z:.0f})" for p in places)
            await self.say(f"Places: {listed}" if places else "No places yet. Try #sethome.")
        elif spec.builtin == "help":
            # One line per command: a chat line holds about 250 characters.
            for line in self.vocabulary.help_lines():
                await self.say(line)
        elif spec.code is not None:
            # Work the bot chose from free text needs consent in consult mode, like a task does;
            # a typed command is the player's own explicit request.
            question = f"Should I run {self.vocabulary.prefix}{spec.name}?"
            consult = origin != "typed" and self.autonomy is Autonomy.CONSULT
            if consult and not await self.ask(sender, question):
                return
            await self.say(f"On it: {spec.name}.")
            code, args = spec.code, invocation.args
            await self._start(lambda: self._run_command(spec.name, code, args))
        else:
            await self.say(f"I do not know how to do {spec.name} yet.")

    async def task(self, goal: str, sender: str) -> None:
        if self.autonomy is Autonomy.CONSULT and not await self.ask(sender, f"Should I: {goal}?"):
            return
        await self.say(f"Working on: {goal}")
        await self._start(lambda: self._run_goal(goal))

    async def ask(self, sender: str, question: str) -> bool:
        """Consult mode only. No answer within the timeout means no (it never grants permission)."""
        if self._question is not None:
            await self.say("I am waiting for another answer; ask me again in a moment.")
            return False
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._question = (sender, future)
        await self.say(f"{question} (yes/no, {self.ask_timeout_s:.0f} s)")
        try:
            async with asyncio.timeout(self.ask_timeout_s):
                approved = await future
        except TimeoutError:
            await self.say("No answer, so I will not do it.")
            return False
        finally:
            self._question = None
        if not approved:
            await self.say("Okay, I will not.")
        return approved

    async def stop(self) -> bool:
        # #stop also withdraws an open question: a later "yes" must not start what was stopped.
        if self._question is not None and not self._question[1].done():
            self._question[1].set_result(False)
        async with self._work_lock:
            return await self._stop_locked()

    async def _stop_locked(self) -> bool:
        work = self._work
        self._work = None
        if work is None or work.done():
            return False
        work.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await work
        try:
            await self.bot.interrupt()
        except PluginError as error:
            _log.warning("cannot interrupt: %s", error)
        return True

    async def say(self, text: str) -> None:
        line = " ".join(text.split())[:MAX_CHAT]
        try:
            await self.bot.chat(line)
        except PluginError as error:
            _log.warning("cannot chat: %s", error)

    def _mentions_me(self, message: str) -> bool:
        # A whole word: "QABot2, are you there?" is for another player, not for QABot.
        return (
            re.search(rf"(?<!\w){re.escape(self.name)}(?!\w)", message, re.IGNORECASE) is not None
        )

    def _answer(self, sender: str, message: str) -> bool:
        if self._question is None or self._question[0] != sender:
            return False
        # "QABot yes" / "yes, QABot!" answer the question too.
        without_name = re.sub(
            rf"(?<!\w){re.escape(self.name)}(?!\w)", " ", message, flags=re.IGNORECASE
        )
        words = " ".join(re.sub(r"[^\w' ]", " ", without_name).lower().split())
        future = self._question[1]
        if future.done():
            return False
        if words in YES:
            future.set_result(True)
            return True
        if words in NO:
            future.set_result(False)
            return True
        return False

    def _place_position(self, name: str) -> JsonObject | None:
        place = self.places.get(self.world, name)
        if place is None:
            return None
        position: JsonObject = {"x": place.x, "y": place.y, "z": place.z}
        if place.dimension is not None:
            position["dimension"] = place.dimension
        return position

    async def _remember(self, name: str, sender: str) -> None:
        observation = await self.bot.observe()
        position, dimension = observation.get("position"), observation.get("dimension")
        if not isinstance(position, dict):
            await self.say("I do not know where I am right now.")
            return
        coords = [position.get(axis) for axis in ("x", "y", "z")]
        if not all(isinstance(c, int | float) for c in coords):
            await self.say("I do not know where I am right now.")
            return
        x, y, z = (float(c) for c in coords if isinstance(c, int | float))
        try:
            place = self.places.save(
                self.world,
                name,
                (x, y, z),
                dimension=dimension if isinstance(dimension, str) else None,
                saved_by=sender,
            )
        except PlaceError as error:
            await self.say(str(error))
            return
        await self.say(f"Saved {place.name} at {x:.0f} {y:.0f} {z:.0f}.")

    async def _start(self, work: Callable[[], Awaitable[None]]) -> None:
        # One piece of work at a time: a new request replaces the old one. The lock makes
        # "stop the old, start the new" one step, so two requests cannot both start.
        async with self._work_lock:
            await self._stop_locked()

            async def guarded() -> None:
                try:
                    await work()
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    _log.exception("work failed")
                    await self.say(f"That failed: {error}")

            self._work = asyncio.create_task(guarded())

    async def _run_command(self, name: str, code: str, args: JsonObject) -> None:
        if await self._wrong_dimension(args):
            await self.say(f"That place is in another dimension; I cannot {name} there from here.")
            return
        result = await self.bot.run_skill(code, args, COMMAND_TIMEOUT_S)
        partial = isinstance(result.result, dict) and result.result.get("complete") is False
        if result.ok and partial:
            await self.say(f"Partly done: {name} ({result.result}).")
        elif result.ok:
            await self.say(f"Done: {name}.")
        elif result.status != "cancelled" or "reflex" in (result.error or ""):
            await self.say(f"{name} stopped: {result.error or result.status}")

    async def _wrong_dimension(self, args: JsonObject) -> bool:
        """A place saved in another dimension has coordinates that mean nothing here."""
        target = args.get("target")
        wanted = target.get("dimension") if isinstance(target, dict) else None
        if not isinstance(wanted, str):
            return False
        here = (await self.bot.observe()).get("dimension")
        return isinstance(here, str) and wanted != here

    async def _run_goal(self, goal: str) -> None:
        await self.say(await self.run_task(goal))


@dataclass(frozen=True, slots=True)
class PluginBot:
    """`BotPort` over a plugin's main process."""

    plugin: PluginClient

    async def chat(self, text: str) -> None:
        await self.plugin.act("chat", {"text": text})

    async def observe(self) -> JsonObject:
        return await self.plugin.observe({"nearby": False})

    async def run_skill(self, code: str, args: JsonObject, timeout_s: float) -> SkillResult:
        return await run_skill(self.plugin, code, args, timeout_s=timeout_s)

    async def interrupt(self) -> None:
        await self.plugin.request("interrupt")


def _objects(value: JsonValue) -> list[JsonObject]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


async def serve(args: argparse.Namespace) -> None:
    llm = LlmClient(AnthropicBackend(), TelemetryRecorder(Path("runs/telemetry/agent.jsonl")))
    library = SkillLibrary(Path("runs/skills.sqlite"))
    places = PlaceStore(Path("runs/memory/places.sqlite"))
    async with await PluginClient.start(args.plugin_dir) as plugin:
        hello = await plugin.handshake()
        name = (await plugin.observe({"nearby": False})).get("username")
        world = hello.get("world")
        level = world.get("level") if isinstance(world, dict) else None
        guide = hello.get("skillGuide")
        voyager = VoyagerAgent(
            llm, library, _objects(hello.get("skillApi")), guide if isinstance(guide, str) else ""
        )
        session = PluginSession(plugin)

        async def run_goal(goal: str) -> str:
            outcome = await voyager.solve(Task("chat", goal), session, trace_id=new_trace_id())
            if outcome.verdict.value == "true":
                return f"Done: {goal} (skill {outcome.learned_skill or 'reused'})."
            return f"I could not: {outcome.reason or outcome.verdict.value}."

        providers: list[ChoiceProvider] = [KeywordRule()]
        try:
            providers.insert(0, JevProvider())
        except TypeSafeError as error:
            # No TypeSafe key: L1 still works with the rule alone (it never acts on the rule).
            print(f"L1: Jev unavailable ({error}); using the keyword rule only")
        decisions = DecisionClient(providers, Path("runs/telemetry/decisions.jsonl"))
        runtime = AgentRuntime(
            PluginBot(plugin),
            str(name),
            Vocabulary.from_handshake(hello.get("commands")),
            places,
            level if isinstance(level, str) else "world",
            llm,
            Autonomy(args.autonomy),
            run_goal,
            decisions=decisions,
            l1_act=args.l1 == "act",
        )
        await runtime.say(f"Hello! I am {name} ({args.autonomy} mode). Try #help.")
        print(f"{name} is listening ({args.autonomy} mode). Ctrl-C to stop.")
        handlers: set[asyncio.Task[None]] = set()
        while True:
            event = await plugin.next_event(timeout_s=3_600)
            kind = event.get("type")
            if kind == "chat":
                sender, message = event.get("sender"), event.get("message")
                if isinstance(sender, str) and isinstance(message, str):
                    handler = asyncio.create_task(runtime.on_chat(sender, message))
                    handlers.add(handler)
                    handler.add_done_callback(handlers.discard)
            elif kind in ("reflex", "death", "disconnected", "kicked"):
                print(f"event: {event}")
                if kind == "disconnected":
                    return


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the agent: chat commands, tasks, persona.")
    parser.add_argument("plugin_dir", type=Path)
    parser.add_argument("--autonomy", choices=[a.value for a in Autonomy], default="full")
    parser.add_argument(
        "--l1", choices=["shadow", "act"], default="shadow", help="L1 command routing mode"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    try:
        asyncio.run(serve(args))
    except KeyboardInterrupt:
        return 0
    except (ManifestError, PluginError, TimeoutError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
