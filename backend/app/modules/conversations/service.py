"""Conversation storage. Every function takes the acting user's id and filters on it: a
conversation that belongs to someone else behaves exactly like one that doesn't exist."""

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.conversations.models import Conversation, Message

TITLE_MAX_CHARS = 60


class ConversationNotFoundError(AppError):
    # 404, not 403: a 403 would confirm that the id exists and belongs to someone else.
    status_code = 404
    code = "conversation_not_found"

    def __init__(self) -> None:
        super().__init__("Conversation not found")


@dataclass(frozen=True)
class AssistantReply:
    """What the AI layer hands back for storage. Plain data, so this module needs no AI imports."""

    content: str
    model: str
    prompt_version: str
    # None when unknown, e.g. a reply the user stopped before the provider reported usage.
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: Decimal | None
    latency_ms: int | None
    finish_reason: str


def title_from_message(text: str) -> str:
    """A cheap, deterministic title: the first words of the opening message."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= TITLE_MAX_CHARS:
        return collapsed
    return collapsed[: TITLE_MAX_CHARS - 1].rstrip() + "…"


async def list_conversations(db: AsyncSession, user_id: uuid.UUID, limit: int = 50) -> list[Conversation]:
    rows = await db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
    )
    return list(rows)


async def get_conversation(db: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
    conversation = await db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    if conversation is None:
        raise ConversationNotFoundError()
    return conversation


async def list_messages(
    db: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID, *, last: int | None = None
) -> list[Message]:
    """Messages in chronological order; with `last`, only the most recent `last` of them."""
    await get_conversation(db, user_id, conversation_id)  # ownership check, raises 404
    query = select(Message).where(Message.conversation_id == conversation_id, Message.user_id == user_id)
    if last is None:
        rows = await db.scalars(query.order_by(Message.created_at, Message.id))
        return list(rows)
    # Newest first to apply the limit, then flip back to chronological order.
    rows = await db.scalars(query.order_by(Message.created_at.desc(), Message.id.desc()).limit(last))
    return list(reversed(list(rows)))


async def record_turn(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    user_text: str,
    reply: AssistantReply,
    *,
    new_conversation_id: uuid.UUID | None = None,
) -> tuple[Conversation, Message, Message]:
    """Store one user message and its reply atomically: both are saved, or neither is.

    With `conversation_id=None` a new conversation is started and titled from `user_text`, using
    `new_conversation_id` if given (streaming announces the id before anything is stored).
    """
    if conversation_id is None:
        conversation = Conversation(
            id=new_conversation_id or uuid.uuid7(), user_id=user_id, title=title_from_message(user_text)
        )
        db.add(conversation)
        await db.flush()
    else:
        # Re-checked here, not only before the LLM call: the conversation may have been
        # deleted while the model was answering.
        conversation = await get_conversation(db, user_id, conversation_id)
        conversation.updated_at = func.now()

    # Created in order, so the UUIDv7 ids sort user-then-assistant even though both rows get
    # the same created_at (now() is the transaction's start time).
    user_message = Message(conversation_id=conversation.id, user_id=user_id, role="user", content=user_text)
    assistant_message = Message(
        conversation_id=conversation.id,
        user_id=user_id,
        role="assistant",
        content=reply.content,
        model=reply.model,
        prompt_version=reply.prompt_version,
        input_tokens=reply.input_tokens,
        output_tokens=reply.output_tokens,
        cost_usd=reply.cost_usd,
        latency_ms=reply.latency_ms,
        finish_reason=reply.finish_reason,
    )
    db.add_all([user_message, assistant_message])
    try:
        await db.commit()
    except IntegrityError as exc:
        # Deleted between the check above and the insert (foreign key violation).
        await db.rollback()
        raise ConversationNotFoundError() from exc
    await db.refresh(conversation)
    return conversation, user_message, assistant_message


async def delete_conversation(db: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID) -> None:
    """Delete a conversation and (by cascade) all its messages."""
    result = await db.execute(
        delete(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise ConversationNotFoundError()
    await db.commit()
