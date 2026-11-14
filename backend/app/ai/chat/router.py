from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai.chat.schemas import ChatRequest, ChatResponse
from app.ai.chat.service import AssistantFailedError, run_chat_turn
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
    """Send a message and get the assistant's reply. Omit `conversation_id` to start a new conversation."""
    turn = await run_chat_turn(
        db, provider, user_id=user.id, conversation_id=body.conversation_id, text=body.message, today=date.today()
    )
    return ChatResponse(
        conversation=ConversationRead.model_validate(turn.conversation),
        user_message=MessageRead.model_validate(turn.user_message),
        assistant_message=MessageRead.model_validate(turn.assistant_message),
    )
