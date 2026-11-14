import uuid

from fastapi import APIRouter, Response

from app.db.session import DbSession
from app.modules.auth.dependencies import CurrentUser
from app.modules.conversations import service
from app.modules.conversations.schemas import ConversationDetail, ConversationRead, MessageRead

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationRead])
async def list_conversations(user: CurrentUser, db: DbSession) -> list[ConversationRead]:
    conversations = await service.list_conversations(db, user.id)
    return [ConversationRead.model_validate(c) for c in conversations]


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ConversationDetail:
    conversation = await service.get_conversation(db, user.id, conversation_id)
    messages = await service.list_messages(db, user.id, conversation_id)
    return ConversationDetail(
        **ConversationRead.model_validate(conversation).model_dump(),
        messages=[MessageRead.model_validate(m) for m in messages],
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    await service.delete_conversation(db, user.id, conversation_id)
    return Response(status_code=204)
