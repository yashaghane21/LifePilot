from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.ai.chat.schemas import ChatRequest, ChatResponse
from app.ai.chat.service import AssistantFailedError, prepare_turn, run_chat_turn, stream_chat_turn
from app.ai.providers.base import LLMError, LLMProvider
from app.ai.providers.factory import get_llm_provider
from app.db.session import DbSession
from app.modules.auth.dependencies import CurrentUser
from app.modules.conversations.schemas import ConversationRead, MessageRead

router = APIRouter(tags=["chat"])


def get_chat_provider() -> LLMProvider:
    """The configured LLM provider. Tests override this dependency with a FakeProvider."""
    try:
        return get_llm_provider()
    except LLMError as exc:  # e.g. OPENROUTER_API_KEY not set
        raise AssistantFailedError("The assistant is not configured.") from exc


ChatProvider = Annotated[LLMProvider, Depends(get_chat_provider)]


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user: CurrentUser, db: DbSession, provider: ChatProvider) -> ChatResponse:
    """Send a message and get the assistant's whole reply at once. Omit `conversation_id` to start a new conversation."""
    turn = await prepare_turn(
        db, user_id=user.id, conversation_id=body.conversation_id, text=body.message, today=date.today()
    )
    result = await run_chat_turn(db, provider, turn)
    return ChatResponse(
        conversation=ConversationRead.model_validate(result.conversation),
        user_message=MessageRead.model_validate(result.user_message),
        assistant_message=MessageRead.model_validate(result.assistant_message),
    )


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "Server-Sent Events"}},
)
async def chat_stream(body: ChatRequest, user: CurrentUser, db: DbSession, provider: ChatProvider) -> StreamingResponse:
    """Like POST /chat, but the reply arrives as Server-Sent Events while it is generated.

    Events: `start` {conversation_id, title} → `delta` {text}… → `done` (same body as POST /chat)
    or `error` {code, message, request_id}. Validation, auth and 404 errors are normal HTTP
    errors, returned before the stream starts.
    """
    # Everything that can fail with a normal HTTP error happens here, before the 200 is sent.
    # prepare_turn also commits, so this request holds no DB connection while streaming.
    turn = await prepare_turn(
        db, user_id=user.id, conversation_id=body.conversation_id, text=body.message, today=date.today()
    )
    return StreamingResponse(
        stream_chat_turn(provider, turn),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tell proxies such as nginx not to buffer the stream (it would arrive all at once).
            "X-Accel-Buffering": "no",
        },
    )
