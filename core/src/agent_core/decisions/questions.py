"""Versioned L1 question definitions (decision 10c). Options come from the plugin's vocabulary,
so the questions name no game."""

from agent_core.commands import Vocabulary
from agent_core.decisions.client import ChoiceQuestion

COMMAND_ROUTE_VERSION = 1
# Measured on the example set before acting on it; until then the point runs in shadow mode.
COMMAND_ROUTE_THRESHOLD = 0.9


def command_route(vocabulary: Vocabulary) -> ChoiceQuestion:
    """Which command (if any) a chat message to the bot asks for."""
    options: dict[str, str] = {}
    keywords: dict[str, list[str]] = {}
    for spec in vocabulary.commands.values():
        options[spec.name] = f"Command {vocabulary.prefix}{spec.name}: {spec.description}"
        keywords[spec.name] = [spec.name, *spec.keywords]
    options["task"] = (
        "The player asks the bot to achieve something in the game that none of the commands "
        "covers (e.g. obtain or craft something, build something)."
    )
    options["chat"] = "Small talk, a question, thanks, or anything that is not a request to act."
    return ChoiceQuestion(
        "command_route",
        COMMAND_ROUTE_VERSION,
        "A player sent `message` to the game bot. Which of these does the player want?",
        options,
        COMMAND_ROUTE_THRESHOLD,
        keywords,
    )
