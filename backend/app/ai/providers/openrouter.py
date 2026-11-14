"""OpenRouter: one API key, many model vendors, OpenAI-compatible chat completions."""

import asyncio
import json
import logging
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

import httpx

from app.ai.providers.base import (
    ChatMessage,
    ChatResult,
    FinishReason,
    LLMAuthError,
    LLMBadRequestError,
    LLMError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMUnavailableError,
    ResponseSchema,
    StreamDone,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolSpec,
    Usage,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_FINISH_REASONS: dict[str, FinishReason] = {
    "stop": "stop",
    "tool_calls": "tool_calls",
    "length": "length",
    "content_filter": "content_filter",
}


def _to_wire(message: ChatMessage) -> dict[str, Any]:
    wire: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        wire["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in message.tool_calls
        ]
    if message.tool_call_id:
        wire["tool_call_id"] = message.tool_call_id
    return wire


def _tool_to_wire(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters},
    }


def _usage(raw: dict[str, Any]) -> Usage:
    return Usage(
        input_tokens=int(raw.get("prompt_tokens") or 0),
        output_tokens=int(raw.get("completion_tokens") or 0),
        cost_usd=float(raw["cost"]) if raw.get("cost") is not None else None,
    )


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        app_url: str = "http://localhost:5173",
        app_name: str = "LifePilot AI",
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.default_model = default_model
        self._max_retries = max_retries
        self._sleep = sleep
        self._client = httpx.AsyncClient(
            base_url=base_url,
            # For streams, `read` is the longest allowed gap between two chunks, not the total time.
            timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                # Optional attribution headers OpenRouter uses for its app rankings.
                "HTTP-Referer": app_url,
                "X-Title": app_name,
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _body(
        self,
        messages: Sequence[ChatMessage],
        model: str | None,
        tools: Sequence[ToolSpec],
        response_schema: ResponseSchema | None,
        max_output_tokens: int,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": [_to_wire(m) for m in messages],
            "max_tokens": max_output_tokens,
            # Ask OpenRouter to include the dollar cost of this call in `usage`.
            "usage": {"include": True},
            # Deliberately no `temperature`: current Claude models reject sampling parameters.
        }
        if tools:
            body["tools"] = [_tool_to_wire(t) for t in tools]
        if response_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": response_schema.name, "strict": True, "schema": response_schema.schema},
            }
        return body

    # ----------------------------------------------------------------- complete

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        tools: Sequence[ToolSpec] = (),
        response_schema: ResponseSchema | None = None,
        max_output_tokens: int = 4096,
    ) -> ChatResult:
        body = self._body(messages, model, tools, response_schema, max_output_tokens)
        started = time.perf_counter()
        attempt = 0
        while True:
            attempt += 1
            try:
                payload = await self._post_once(body)
                break
            except LLMError as exc:
                await self._before_retry(exc, attempt, body["model"])

        result = self._parse(payload, latency_ms=(time.perf_counter() - started) * 1000, attempts=attempt)
        self._log_success(result)
        return result

    async def _post_once(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post("/chat/completions", json=body)
        except httpx.TimeoutException as exc:
            raise LLMUnavailableError("request to OpenRouter timed out") from exc
        except httpx.TransportError as exc:
            raise LLMUnavailableError(f"could not reach OpenRouter: {type(exc).__name__}") from exc

        try:
            payload: dict[str, Any] = response.json()
        except json.JSONDecodeError:
            payload = {}
        # OpenRouter sometimes reports upstream failures as HTTP 200 with an `error` object.
        error = payload.get("error") if isinstance(payload, dict) else None
        if response.status_code == 200 and not error:
            return payload
        raise self._error_from(response, payload)

    # ------------------------------------------------------------------- stream

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        max_output_tokens: int = 4096,
    ) -> AsyncIterator[StreamEvent]:
        body = self._body(messages, model, (), None, max_output_tokens) | {"stream": True}
        started = time.perf_counter()
        attempt = 0
        while True:
            attempt += 1
            emitted = False
            try:
                async with self._client.stream("POST", "/chat/completions", json=body) as response:
                    if response.status_code != 200:
                        await response.aread()
                        try:
                            payload = response.json()
                        except json.JSONDecodeError:
                            payload = {}
                        raise self._error_from(response, payload if isinstance(payload, dict) else {})
                    async for event in self._read_events(response, started, attempt, body["model"]):
                        emitted = emitted or isinstance(event, TextDelta)
                        yield event
                    return
            except LLMError as exc:
                # Retry only if nothing was shown yet: once text has reached the user, a retry would
                # produce a different reply glued onto the first one.
                if emitted:
                    logger.warning("llm_stream_failed", extra={"model": body["model"], "error": type(exc).__name__})
                    raise
                await self._before_retry(exc, attempt, body["model"])
            except httpx.TimeoutException as exc:
                if emitted:
                    raise LLMUnavailableError("OpenRouter stream stalled") from exc
                await self._before_retry(LLMUnavailableError("request to OpenRouter timed out"), attempt, body["model"])
            except httpx.TransportError as exc:
                error = LLMUnavailableError(f"OpenRouter connection failed: {type(exc).__name__}")
                if emitted:
                    raise error from exc
                await self._before_retry(error, attempt, body["model"])

    async def _read_events(
        self, response: httpx.Response, started: float, attempt: int, requested_model: str
    ) -> AsyncIterator[StreamEvent]:
        """Parse an OpenAI-style SSE stream: `data: {json}` lines, ending with `data: [DONE]`."""
        parts: list[str] = []
        finish: str | None = None
        usage: dict[str, Any] = {}
        model = requested_model
        generation_id: str | None = None
        first_token_ms: float | None = None

        async for line in response.aiter_lines():
            # Blank lines separate events; lines starting with ":" are keep-alive comments
            # (OpenRouter sends ": OPENROUTER PROCESSING" while the model is thinking).
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if error := chunk.get("error"):
                # A failure after the stream started arrives as a chunk, not an HTTP status.
                info = error if isinstance(error, dict) else {}
                status = info["code"] if isinstance(info.get("code"), int) else 502
                raise self._error_for_status(status, f"OpenRouter stream error {status}: {info.get('message')}", response)

            model = chunk.get("model") or model
            generation_id = chunk.get("id") or generation_id
            if chunk.get("usage"):
                usage = chunk["usage"]
            for choice in chunk.get("choices") or []:
                # `delta.reasoning` (hidden thinking) is deliberately not forwarded.
                text = (choice.get("delta") or {}).get("content")
                if text:
                    if first_token_ms is None:
                        first_token_ms = (time.perf_counter() - started) * 1000
                    parts.append(text)
                    yield TextDelta(text)
                if choice.get("finish_reason"):
                    finish = choice["finish_reason"]

        result = ChatResult(
            content="".join(parts),
            tool_calls=(),
            finish_reason=_FINISH_REASONS.get(finish or "", "other"),
            usage=_usage(usage),
            model=model,
            latency_ms=(time.perf_counter() - started) * 1000,
            provider_request_id=generation_id,
            attempts=attempt,
            time_to_first_token_ms=first_token_ms,
        )
        self._log_success(result)
        yield StreamDone(result)

    # ------------------------------------------------------------------ shared

    async def _before_retry(self, exc: LLMError, attempt: int, model: str) -> None:
        """Re-raise if `exc` is final; otherwise wait the backoff delay before the next attempt."""
        if not exc.retryable or attempt > self._max_retries:
            logger.warning(
                "llm_call_failed",
                extra={"provider": self.name, "model": model, "attempts": attempt, "error": type(exc).__name__},
            )
            raise exc
        retry_after = exc.retry_after if isinstance(exc, LLMRateLimitError) else None
        delay = self._backoff_delay(attempt, retry_after)
        logger.info("llm_call_retry", extra={"attempt": attempt, "delay_s": round(delay, 2), "error": type(exc).__name__})
        await self._sleep(delay)

    def _log_success(self, result: ChatResult) -> None:
        # Metrics only: never log message content (personal data).
        logger.info(
            "llm_call",
            extra={
                "provider": self.name,
                "model": result.model,
                "input_tokens": result.usage.input_tokens,
                "output_tokens": result.usage.output_tokens,
                "cost_usd": result.usage.cost_usd,
                "latency_ms": round(result.latency_ms),
                "ttft_ms": round(result.time_to_first_token_ms) if result.time_to_first_token_ms is not None else None,
                "finish_reason": result.finish_reason,
                "tool_calls": len(result.tool_calls),
                "attempts": result.attempts,
            },
        )

    @staticmethod
    def _backoff_delay(attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, 30.0)
        # Exponential backoff with full jitter: 0..1s, 0..2s, 0..4s... so many clients
        # that failed together don't all retry at the same instant.
        return random.uniform(0, min(2 ** (attempt - 1), 8))

    def _error_from(self, response: httpx.Response, payload: dict[str, Any]) -> LLMError:
        error = payload.get("error")
        error_info = error if isinstance(error, dict) else {}
        status = response.status_code
        if status == 200:
            # Error inside a 200: use the code it carries, else treat as an upstream failure.
            status = error_info["code"] if isinstance(error_info.get("code"), int) else 502
        detail = f"OpenRouter {status}: {error_info.get('message') or response.reason_phrase}"
        return self._error_for_status(status, detail, response)

    @staticmethod
    def _error_for_status(status: int, detail: str, response: httpx.Response) -> LLMError:
        if status in (401, 403):
            return LLMAuthError(detail)
        if status == 402:
            return LLMQuotaError(detail)
        if status == 429:
            retry_after = response.headers.get("retry-after")
            return LLMRateLimitError(detail, float(retry_after) if retry_after and retry_after.isdigit() else None)
        if status in RETRYABLE_STATUS or status >= 500:
            return LLMUnavailableError(detail)
        return LLMBadRequestError(detail)

    def _parse(self, payload: dict[str, Any], *, latency_ms: float, attempts: int) -> ChatResult:
        try:
            choice = payload["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMUnavailableError("OpenRouter response had no choices") from exc

        tool_calls = tuple(
            ToolCall(id=c["id"], name=c["function"]["name"], arguments=c["function"].get("arguments") or "{}")
            for c in message.get("tool_calls") or []
        )
        return ChatResult(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=_FINISH_REASONS.get(choice.get("finish_reason") or "", "other"),
            usage=_usage(payload.get("usage") or {}),
            model=payload.get("model") or "unknown",
            latency_ms=latency_ms,
            provider_request_id=payload.get("id"),
            attempts=attempts,
        )
