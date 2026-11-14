"""One chat turn: load history → build context → call the model → store both messages.

Two ways to run a turn:
- run_chat_turn: wait for the whole reply, return it (POST /chat).
- stream_chat_turn: send the reply as it is generated, as Server-Sent Events (POST /chat/stream).
"""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Coroutine
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.chat.context import MAX_HISTORY_MESSAGES, PastMessage, build_messages
from app.ai.chat.schemas import ChatResponse
from app.ai.prompts.system import PROMPT_VERSION
from app.ai.providers.base import ChatMessage, ChatResult, LLMError, LLMProvider, StreamDone, TextDelta
from app.core.errors import AppError
from app.core.logging import request_id_var
from app.db.session import SessionLocal
from app.modules.conversations import service as conversations
from app.modules.conversations.models import Conversation, Message
from app.modules.conversations.schemas import ConversationRead, MessageRead

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


def _client_error(exc: LLMError) -> AppError:
    # The provider already logged the details; the client gets a generic message.
    if exc.retryable:
        return AssistantUnavailableError("The assistant is busy right now. Please try again.")
    return AssistantFailedError("The assistant could not answer. Please try again later.")


@dataclass(frozen=True)
class ChatTurn:
    conversation: Conversation
    user_message: Message
    assistant_message: Message


@dataclass(frozen=True)
class PreparedTurn:
    """Everything needed to call the model, gathered before any tokens are spent."""

    user_id: uuid.UUID
    text: str
    # None: this turn starts a new conversation.
    conversation_id: uuid.UUID | None
    # The id the conversation has, or will have once this turn is stored.
    target_id: uuid.UUID
    title: str
    messages: list[ChatMessage]


async def prepare_turn(
    db: AsyncSession, *, user_id: uuid.UUID, conversation_id: uuid.UUID | None, text: str, today: date
) -> PreparedTurn:
    history: list[Message] = []
    if conversation_id is None:
        target_id, title = uuid.uuid7(), conversations.title_from_message(text)
    else:
        # Raises 404 for a missing conversation or someone else's, before any tokens are spent.
        conversation = await conversations.get_conversation(db, user_id, conversation_id)
        target_id, title = conversation.id, conversation.title
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
    return PreparedTurn(user_id, text, conversation_id, target_id, title, messages)


def _reply_from(result: ChatResult) -> conversations.AssistantReply:
    content = (result.content or "").strip()
    if not content:
        # e.g. a reasoning model that used its whole token budget on thinking. Storing an empty
        # reply would also poison the history sent on later turns.
        logger.warning("chat_empty_reply", extra={"model": result.model, "finish_reason": result.finish_reason})
        raise AssistantFailedError("The assistant returned an empty reply. Please try again.")
    return conversations.AssistantReply(
        content=content,
        model=result.model,
        prompt_version=PROMPT_VERSION,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        cost_usd=_to_money(result.usage.cost_usd),
        latency_ms=round(result.latency_ms),
        finish_reason=result.finish_reason,
    )


async def _store(db: AsyncSession, turn: PreparedTurn, reply: conversations.AssistantReply) -> ChatTurn:
    conversation, user_message, assistant_message = await conversations.record_turn(
        db, turn.user_id, turn.conversation_id, turn.text, reply, new_conversation_id=turn.target_id
    )
    logger.info(
        "chat_turn",
        extra={
            "conversation_id": str(conversation.id),
            "new_conversation": turn.conversation_id is None,
            "history_messages": len(turn.messages) - 2,
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
            "finish_reason": reply.finish_reason,
        },
    )
    return ChatTurn(conversation, user_message, assistant_message)


async def _store_in_new_session(turn: PreparedTurn, reply: conversations.AssistantReply) -> ChatTurn:
    async with SessionLocal() as db:
        return await _store(db, turn, reply)


# ---------------------------------------------------------------- whole reply


async def run_chat_turn(db: AsyncSession, provider: LLMProvider, turn: PreparedTurn) -> ChatTurn:
    try:
        result = await provider.complete(turn.messages, max_output_tokens=MAX_OUTPUT_TOKENS)
    except LLMError as exc:
        raise _client_error(exc) from exc
    return await _store(db, turn, _reply_from(result))


# -------------------------------------------------------------------- streaming

# Saves that must finish even though the request that started them was cancelled. A plain
# asyncio task can be garbage-collected mid-flight unless something holds a reference to it.
_background_saves: set[asyncio.Task[Any]] = set()


def _run_in_background(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    task = asyncio.create_task(coro)
    _background_saves.add(task)
    task.add_done_callback(_background_saves.discard)
    return task


async def drain_background_saves() -> None:
    """Wait for in-flight saves (app shutdown, tests)."""
    if _background_saves:
        await asyncio.gather(*_background_saves, return_exceptions=True)


def sse(event: str, data: dict[str, Any]) -> str:
    """One Server-Sent Event. json.dumps escapes newlines, so `data` is always a single line."""
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'), ensure_ascii=False)}\n\n"


def _sse_error(error: AppError) -> str:
    return sse("error", {"code": error.code, "message": error.message, "request_id": request_id_var.get()})


async def _save_stopped_reply(turn: PreparedTurn, partial: str, model: str) -> None:
    """The user pressed Stop (or closed the tab) mid-reply: keep what they already saw."""
    reply = conversations.AssistantReply(
        content=partial,
        model=model,
        prompt_version=PROMPT_VERSION,
        # The provider reports usage only at the end of a stream, so it is unknown here.
        input_tokens=None,
        output_tokens=None,
        cost_usd=None,
        latency_ms=None,
        finish_reason="cancelled",
    )
    try:
        await _store_in_new_session(turn, reply)
    except Exception:
        # e.g. the conversation was deleted meanwhile. Nobody is waiting for this result.
        logger.exception("chat_stopped_reply_not_saved")


async def stream_chat_turn(provider: LLMProvider, turn: PreparedTurn) -> AsyncIterator[str]:
    """Server-Sent Events for one turn: `start`, `delta`..., then `done` or `error`.

    The turn is stored only when the reply is complete, except when the client disconnects
    mid-reply: then the text it already received is stored with finish_reason "cancelled".
    """
    yield sse("start", {"conversation_id": str(turn.target_id), "title": turn.title})

    parts: list[str] = []
    result: ChatResult | None = None
    try:
        async for event in provider.stream(turn.messages, max_output_tokens=MAX_OUTPUT_TOKENS):
            if isinstance(event, TextDelta):
                parts.append(event.text)
                yield sse("delta", {"text": event.text})
            elif isinstance(event, StreamDone):
                result = event.result
    except LLMError as exc:
        # A failed reply is not stored, even if some of it was already shown.
        yield _sse_error(_client_error(exc))
        return
    except (asyncio.CancelledError, GeneratorExit):
        # Client disconnected. No awaiting here: the request is being torn down, so the save
        # runs as its own task. (CancelledError comes from the server cancelling the request;
        # GeneratorExit from the generator being closed.)
        partial = "".join(parts).strip()
        if partial:
            _run_in_background(_save_stopped_reply(turn, partial, provider.default_model))
        raise

    if result is None:
        yield _sse_error(AssistantUnavailableError("The reply ended unexpectedly. Please try again."))
        return
    try:
        reply = _reply_from(result)
    except AssistantFailedError as exc:
        yield _sse_error(exc)
        return

    # Shielded: if the client disconnects now, the complete reply is still stored.
    try:
        stored = await asyncio.shield(_run_in_background(_store_in_new_session(turn, reply)))
    except AppError as exc:  # e.g. the conversation was deleted while the model was answering
        yield _sse_error(exc)
        return

    response = ChatResponse(
        conversation=ConversationRead.model_validate(stored.conversation),
        user_message=MessageRead.model_validate(stored.user_message),
        assistant_message=MessageRead.model_validate(stored.assistant_message),
    )
    yield sse("done", response.model_dump(mode="json"))
