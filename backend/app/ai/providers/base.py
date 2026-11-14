"""The provider-neutral LLM interface. Everything outside `app.ai.providers` uses only these types."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ToolCall:
    """A function call the model asked for. `arguments` is the raw JSON string: validate before use."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str | None = None
    # Set on assistant messages that requested tools.
    tool_calls: tuple[ToolCall, ...] = ()
    # Set on role="tool" messages: which call this result answers.
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    """A function the model may call, described by a JSON Schema for its arguments."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ResponseSchema:
    """Constrain the reply to JSON matching `schema` (structured output)."""

    name: str
    schema: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    # USD as reported by the provider, when it reports it.
    cost_usd: float | None = None


FinishReason = Literal["stop", "tool_calls", "length", "content_filter", "other"]


@dataclass(frozen=True)
class ChatResult:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    finish_reason: FinishReason
    usage: Usage
    model: str
    latency_ms: float
    provider_request_id: str | None = None
    attempts: int = field(default=1)
    # Streaming only: how long until the first visible text arrived (what users perceive as speed).
    time_to_first_token_ms: float | None = None


@dataclass(frozen=True)
class TextDelta:
    """A piece of reply text, emitted as soon as the provider sends it."""

    text: str


@dataclass(frozen=True)
class StreamDone:
    """The final event of a stream: the complete reply with usage and finish reason."""

    result: ChatResult


StreamEvent = TextDelta | StreamDone


class LLMError(Exception):
    """Base for provider failures. Messages are safe to log: they never contain prompts or keys."""

    retryable: bool = False


class LLMAuthError(LLMError):
    """Missing or invalid API key."""


class LLMQuotaError(LLMError):
    """The account is out of credit."""


class LLMBadRequestError(LLMError):
    """The provider rejected the request itself (unknown model, bad parameter...). Fix the code."""


class LLMRateLimitError(LLMError):
    retryable = True

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        # Seconds the provider asked us to wait, from the Retry-After header.
        self.retry_after = retry_after


class LLMUnavailableError(LLMError):
    """Timeouts, connection failures and provider-side errors."""

    retryable = True


class LLMProvider(Protocol):
    name: str
    default_model: str

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        tools: Sequence[ToolSpec] = (),
        response_schema: ResponseSchema | None = None,
        max_output_tokens: int = 4096,
    ) -> ChatResult: ...

    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        max_output_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        """Yield TextDelta events as text arrives, then exactly one StreamDone.

        Closing the iterator early (user pressed Stop) closes the connection to the provider.
        """
        ...

    async def aclose(self) -> None: ...
