"""The keyword rule: the L0 baseline every L1 point must beat (decision 10d), and the fallback.

Counts which option's keywords appear in the text. One clear winner gets confidence 1.0; a tie or
no match falls to the `none`-like default option with low confidence, so the caller escalates.
"""

import re

from agent_core.decisions.client import ChoiceQuestion, ProviderAnswer
from agent_core.plugins import JsonObject


class KeywordRule:
    name = "rules"

    def __init__(self, text_field: str = "message", default_option: str = "chat") -> None:
        self._field = text_field
        self._default = default_option

    async def choose(self, question: ChoiceQuestion, state: JsonObject) -> ProviderAnswer:
        text = str(state.get(self._field, "")).lower()
        words = set(re.findall(r"[a-z0-9_]+", text))
        scores: dict[str, int] = {}
        for option, keywords in question.keywords.items():
            hits = sum(
                1
                for keyword in keywords
                if (keyword in words if " " not in keyword else keyword in text)
            )
            if hits:
                scores[option] = hits
        best = max(scores.values(), default=0)
        winners = [option for option, score in scores.items() if score == best]
        if best > 0 and len(winners) == 1:
            choice, confidence = winners[0], 1.0
        else:
            choice, confidence = self._default, 0.3
        probabilities = {option: (1.0 if option == choice else 0.0) for option in question.options}
        return ProviderAnswer(choice, probabilities, confidence, "keyword-rule-v1")
