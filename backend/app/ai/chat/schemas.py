import uuid
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.modules.conversations.schemas import ConversationRead, MessageRead

# Long enough for a pasted paragraph or two; short enough to bound the cost of one request.
MAX_MESSAGE_CHARS = 8000

UserText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)]


class ChatRequest(BaseModel):
    # Omit to start a new conversation.
    conversation_id: uuid.UUID | None = None
    message: UserText


class ChatResponse(BaseModel):
    conversation: ConversationRead
    user_message: MessageRead
    assistant_message: MessageRead
