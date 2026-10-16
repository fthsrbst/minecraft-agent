import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from agent_core.commands import Vocabulary
from agent_core.decisions.client import (
    ChoiceQuestion,
    DecisionClient,
    DecisionError,
    ProviderAnswer,
)
from agent_core.decisions.questions import command_route
from agent_core.decisions.rules import KeywordRule
from agent_core.plugins import JsonObject

QUESTION = ChoiceQuestion(
    "route", 1, "Which?", {"follow": "f", "stop": "s", "chat": "c"}, 0.8,
    {"follow": ["follow", "with me"], "stop": ["stop", "halt"]},
)  # fmt: skip


@dataclass
class Fixed:
    name: str
    answer: ProviderAnswer | None = None
    error: Exception | None = None
    delay: float = 0.0

    async def choose(self, question: ChoiceQuestion, state: JsonObject) -> ProviderAnswer:
        await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        assert self.answer is not None
        return self.answer


def answer(choice: str, confidence: float) -> ProviderAnswer:
    return ProviderAnswer(choice, {choice: confidence}, confidence, "test-model")


def test_confident_answer_is_accepted_and_logged(tmp_path: Path) -> None:
    client = DecisionClient([Fixed("jev", answer("follow", 0.95))], tmp_path / "d.jsonl")
    decision = asyncio.run(client.decide(QUESTION, {"message": "follow me"}, trace_id="t1"))
    assert (decision.choice, decision.accepted, decision.provider) == ("follow", True, "jev")
    [line] = (tmp_path / "d.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert record["question_id"] == "route"
    assert record["state"] == {"message": "follow me"}
    assert record["model"] == "test-model"


def test_low_confidence_is_not_accepted(tmp_path: Path) -> None:
    client = DecisionClient([Fixed("jev", answer("stop", 0.5))], tmp_path / "d.jsonl")
    decision = asyncio.run(client.decide(QUESTION, {"message": "hmm"}))
    assert decision.choice == "stop" and not decision.accepted


@pytest.mark.parametrize(
    "broken",
    [
        Fixed("jev", error=DecisionError("503")),
        Fixed("jev", answer=answer("follow", 1.0), delay=0.5),  # slower than the timeout
        Fixed("jev", answer=answer("fly", 1.0)),  # not an option
    ],
)
def test_a_failing_provider_falls_back_to_the_next(tmp_path: Path, broken: Fixed) -> None:
    client = DecisionClient([broken, KeywordRule()], tmp_path / "d.jsonl", timeout_s=0.1)
    decision = asyncio.run(client.decide(QUESTION, {"message": "please stop now"}))
    assert (decision.choice, decision.provider) == ("stop", "rules")
    assert decision.fell_back and decision.fell_back[0].startswith("jev")


def test_no_provider_answers_means_no_decision(tmp_path: Path) -> None:
    client = DecisionClient([Fixed("jev", error=DecisionError("down"))], tmp_path / "d.jsonl")
    decision = asyncio.run(client.decide(QUESTION, {"message": "x"}))
    assert (decision.choice, decision.accepted) == (None, False)


@pytest.mark.parametrize(
    ("message", "choice", "confidence"),
    [
        ("follow me", "follow", 1.0),
        ("come along with me", "follow", 1.0),
        ("thanks a lot", "chat", 0.3),
        ("stop, then follow", "chat", 0.3),  # a tie: the rule does not guess
    ],
)
def test_keyword_rule(message: str, choice: str, confidence: float) -> None:
    result = asyncio.run(KeywordRule().choose(QUESTION, {"message": message}))
    assert (result.choice, result.confidence) == (choice, confidence)


def test_command_route_question_comes_from_the_vocabulary() -> None:
    vocabulary = Vocabulary.from_handshake(
        {"commands": [{"name": "follow", "usage": "#follow", "description": "Follow a player.",
                       "args": [], "code": "x", "keywords": ["with me"]}]}
    )  # fmt: skip
    question = command_route(vocabulary)
    assert set(question.options) == {"follow", "task", "chat"}
    assert question.keywords["follow"] == ["follow", "with me"]
    assert "Follow a player." in question.options["follow"]
