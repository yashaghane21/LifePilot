"""One chat turn: load history → build context → call the model → store both messages."""

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.chat.context import MAX_HISTORY_MESSAGES, PastMessage, build_messages
from app.ai.prompts.system import PROMPT_VERSION
from app.ai.providers.base import LLMError, LLMProvider
from app.core.errors import AppError
from app.modules.conversations import service as conversations
from app.modules.conversations.models import Conversation, Message

logger = logging.getLogger(__name__)

# Cap on reply length (and therefore on the cost of one reply). Reasoning models spend part of
# this budget on hidden "thinking" tokens, so it is set well above a typical visible answer.
MAX_OUTPUT_TOKENS = 4096
COST_QUANTUM = Decimal("0.00000001")  # matches messages.cost_usd NUMERIC(12, 8)


class AssistantUnavailableError(AppError):
    """Temporary: rate limited, timed out or provider down. The client may retry."""

    status_code = 503
    code = "assistant_unavailable"


class AssistantFailedError(AppError):
    """Not fixable by retrying (bad configuration, out of credit, unusable reply)."""

    status_code = 502
    code = "assistant_failed"


def _to_money(cost_usd: float | None) -> Decimal | None:
    # Via str: Decimal(0.1) carries float noise, Decimal("0.1") does not. Quantised to the
    # column's 8 decimal places so the API returns the same string before and after storage.
    return None if cost_usd is None else Decimal(str(cost_usd)).quantize(COST_QUANTUM)


@dataclass(frozen=True)
class ChatTurn:
    conversation: Conversation
    user_message: Message
    assistant_message: Message


async def run_chat_turn(
    db: AsyncSession,
    provider: LLMProvider,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    text: str,
    today: date,
) -> ChatTurn:
    history: list[Message] = []
    if conversation_id is not None:
        # Raises 404 for a missing conversation or someone else's, before any tokens are spent.
        history = await conversations.list_messages(db, user_id, conversation_id, last=MAX_HISTORY_MESSAGES)

    # End the read transaction so its pooled connection is returned while we wait on the model.
    # An LLM call takes seconds; holding a connection that long would exhaust a small pool
    # (ours has 5) with only a handful of concurrent chats.
    await db.commit()

    messages = build_messages(
        [PastMessage(role=m.role, content=m.content) for m in history],  # type: ignore[arg-type]
        text,
        today=today,
    )
    try:
        result = await provider.complete(messages, max_output_tokens=MAX_OUTPUT_TOKENS)
    except LLMError as exc:
        # The provider already logged the details; the client gets a generic message.
        if exc.retryable:
            raise AssistantUnavailableError("The assistant is busy right now. Please try again.") from exc
        raise AssistantFailedError("The assistant could not answer. Please try again later.") from exc

    content = (result.content or "").strip()
    if not content:
        # e.g. a reasoning model that used its whole token budget on thinking. Storing an empty
        # reply would also poison the history sent on later turns.
        logger.warning("chat_empty_reply", extra={"model": result.model, "finish_reason": result.finish_reason})
        raise AssistantFailedError("The assistant returned an empty reply. Please try again.")

    reply = conversations.AssistantReply(
        content=content,
        model=result.model,
        prompt_version=PROMPT_VERSION,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        cost_usd=_to_money(result.usage.cost_usd),
        latency_ms=round(result.latency_ms),
        finish_reason=result.finish_reason,
    )
    conversation, user_message, assistant_message = await conversations.record_turn(
        db, user_id, conversation_id, text, reply
    )
    logger.info(
        "chat_turn",
        extra={
            "conversation_id": str(conversation.id),
            "new_conversation": conversation_id is None,
            "history_messages": len(messages) - 2,
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
        },
    )
    return ChatTurn(conversation, user_message, assistant_message)
