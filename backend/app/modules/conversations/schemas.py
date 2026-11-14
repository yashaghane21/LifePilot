import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_serializer


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    # Assistant messages only (null for user messages). Shown in the assistant's trace panel.
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    # Serialised as a decimal string, like all money in the API.
    cost_usd: Decimal | None = None
    latency_ms: int | None = None
    finish_reason: str | None = None

    @field_serializer("cost_usd")
    def _fixed_point(self, value: Decimal | None) -> str | None:
        # Fixed-point always: a zero read back from NUMERIC(12,8) is Decimal('0E-8'), which would
        # otherwise serialise in scientific notation.
        return None if value is None else format(value, "f")


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]
