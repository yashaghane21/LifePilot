"""Context building: which past messages the model sees on this turn.

LLMs are stateless. The model remembers nothing between calls; "memory" in a chat is us
resending the history each time. That history costs input tokens on every turn and must fit in
the context window, so we send only a recent window of it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.ai.prompts.system import system_prompt
from app.ai.providers.base import ChatMessage, Role

# At most this many past messages (10 user/assistant exchanges)...
MAX_HISTORY_MESSAGES = 20
# ...and at most roughly this much text. ~4 characters per token for English, so ~6k tokens.
MAX_HISTORY_CHARS = 24_000


@dataclass(frozen=True)
class PastMessage:
    role: Role
    content: str


def build_messages(
    history: Sequence[PastMessage],
    new_user_text: str,
    *,
    today: date,
    max_messages: int = MAX_HISTORY_MESSAGES,
    max_chars: int = MAX_HISTORY_CHARS,
) -> list[ChatMessage]:
    """System prompt + the newest history that fits the budgets + the new user message."""
    kept: list[PastMessage] = []
    used = 0
    # Walk backwards from the newest message: recent context matters most.
    for message in reversed(history[-max_messages:] if max_messages else []):
        used += len(message.content)
        if used > max_chars:
            break
        kept.append(message)
    kept.reverse()

    # Never open the window with an orphaned assistant reply whose question was trimmed away.
    while kept and kept[0].role != "user":
        kept.pop(0)

    return [
        ChatMessage(role="system", content=system_prompt(today)),
        *(ChatMessage(role=m.role, content=m.content) for m in kept),
        ChatMessage(role="user", content=new_user_text),
    ]
