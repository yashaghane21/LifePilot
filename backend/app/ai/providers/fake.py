"""A scripted provider for tests and offline development: no network, no cost, fully predictable."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.ai.providers.base import ChatMessage, ChatResult, ResponseSchema, ToolCall, ToolSpec, Usage


@dataclass
class RecordedCall:
    messages: list[ChatMessage]
    model: str
    tools: list[ToolSpec]
    response_schema: ResponseSchema | None


@dataclass
class FakeProvider:
    name: str = "fake"
    default_model: str = "fake-model"
    # Replies returned in order; when empty, a short echo of the last user message is returned.
    script: list[ChatResult] = field(default_factory=list)
    calls: list[RecordedCall] = field(default_factory=list)

    def reply(self, content: str | None = None, *, tool_calls: Sequence[ToolCall] = ()) -> None:
        """Queue the next reply."""
        self.script.append(
            ChatResult(
                content=content,
                tool_calls=tuple(tool_calls),
                finish_reason="tool_calls" if tool_calls else "stop",
                usage=Usage(input_tokens=10, output_tokens=5, cost_usd=0.0),
                model=self.default_model,
                latency_ms=1.0,
            )
        )

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        tools: Sequence[ToolSpec] = (),
        response_schema: ResponseSchema | None = None,
        max_output_tokens: int = 4096,
    ) -> ChatResult:
        self.calls.append(RecordedCall(list(messages), model or self.default_model, list(tools), response_schema))
        if self.script:
            return self.script.pop(0)
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return ChatResult(
            content=f"(fake reply) {last_user}",
            tool_calls=(),
            finish_reason="stop",
            usage=Usage(input_tokens=10, output_tokens=5, cost_usd=0.0),
            model=model or self.default_model,
            latency_ms=1.0,
        )

    async def aclose(self) -> None:
        return None
