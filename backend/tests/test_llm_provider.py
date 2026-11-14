"""OpenRouter provider against httpx.MockTransport: what we send, and how we handle every reply."""

import json
from typing import Any

import httpx
import pytest

from app.ai.providers.base import (
    ChatMessage,
    LLMAuthError,
    LLMBadRequestError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMUnavailableError,
    ResponseSchema,
    TextDelta,
    ToolCall,
    ToolSpec,
)
from app.ai.providers.fake import FakeProvider
from app.ai.providers.openrouter import OpenRouterProvider

API_KEY = "sk-or-test-key-must-never-leak"
MESSAGES = [ChatMessage(role="system", content="Be brief."), ChatMessage(role="user", content="Hi")]


def completion(content: str | None = "Hello!", **extra: Any) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if "tool_calls" in extra:
        message["tool_calls"] = extra.pop("tool_calls")
    return {
        "id": "gen-123",
        "model": "anthropic/claude-opus-5.5",
        "choices": [{"message": message, "finish_reason": extra.pop("finish_reason", "stop")}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3, "cost": 0.000108},
    } | extra


class Scripted:
    """Answers each request with the next scripted response and records what was sent."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def body(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[index].content)


def make_provider(server: Scripted, delays: list[float] | None = None, max_retries: int = 2) -> OpenRouterProvider:
    async def record_sleep(seconds: float) -> None:
        if delays is not None:
            delays.append(seconds)

    return OpenRouterProvider(
        api_key=API_KEY,
        default_model="anthropic/claude-opus-5.5",
        transport=httpx.MockTransport(server),
        max_retries=max_retries,
        sleep=record_sleep,  # no real waiting in tests
    )


class TestRequest:
    async def test_sends_model_messages_and_auth(self) -> None:
        server = Scripted(httpx.Response(200, json=completion()))

        await make_provider(server).complete(MESSAGES, max_output_tokens=256)

        request = server.requests[0]
        assert request.url == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["Authorization"] == f"Bearer {API_KEY}"
        body = server.body()
        assert body["model"] == "anthropic/claude-opus-5.5"
        assert body["messages"] == [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"}]
        assert body["max_tokens"] == 256
        assert body["usage"] == {"include": True}

    async def test_never_sends_sampling_parameters(self) -> None:
        server = Scripted(httpx.Response(200, json=completion()))

        await make_provider(server).complete(MESSAGES)

        assert not {"temperature", "top_p", "top_k"} & set(server.body())

    async def test_model_override(self) -> None:
        server = Scripted(httpx.Response(200, json=completion()))

        await make_provider(server).complete(MESSAGES, model="anthropic/claude-haiku-5.5")

        assert server.body()["model"] == "anthropic/claude-haiku-5.5"

    async def test_tools_and_tool_results_use_the_openai_wire_format(self) -> None:
        server = Scripted(httpx.Response(200, json=completion()))
        tool = ToolSpec("log_expense", "Record an expense", {"type": "object", "properties": {"amount": {"type": "string"}}})
        history = [
            *MESSAGES,
            ChatMessage(role="assistant", tool_calls=(ToolCall("call_1", "log_expense", '{"amount":"250"}'),)),
            ChatMessage(role="tool", content='{"ok":true}', tool_call_id="call_1"),
        ]

        await make_provider(server).complete(history, tools=[tool])

        body = server.body()
        assert body["tools"] == [
            {"type": "function", "function": {"name": "log_expense", "description": "Record an expense", "parameters": tool.parameters}}
        ]
        assert body["messages"][2]["tool_calls"][0] == {
            "id": "call_1",
            "type": "function",
            "function": {"name": "log_expense", "arguments": '{"amount":"250"}'},
        }
        assert body["messages"][3] == {"role": "tool", "content": '{"ok":true}', "tool_call_id": "call_1"}

    async def test_structured_output_schema(self) -> None:
        server = Scripted(httpx.Response(200, json=completion('{"amount":"250"}')))
        schema = {"type": "object", "properties": {"amount": {"type": "string"}}, "required": ["amount"]}

        await make_provider(server).complete(MESSAGES, response_schema=ResponseSchema("expense", schema))

        assert server.body()["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "expense", "strict": True, "schema": schema},
        }


class TestResponse:
    async def test_parses_text_usage_and_cost(self) -> None:
        result = await make_provider(Scripted(httpx.Response(200, json=completion()))).complete(MESSAGES)

        assert result.content == "Hello!"
        assert result.finish_reason == "stop"
        assert (result.usage.input_tokens, result.usage.output_tokens) == (12, 3)
        assert result.usage.cost_usd == pytest.approx(0.000108)
        assert result.model == "anthropic/claude-opus-5.5"
        assert result.provider_request_id == "gen-123"

    async def test_parses_tool_calls(self) -> None:
        payload = completion(
            None,
            finish_reason="tool_calls",
            tool_calls=[{"id": "call_9", "type": "function", "function": {"name": "log_expense", "arguments": '{"amount":"250"}'}}],
        )

        result = await make_provider(Scripted(httpx.Response(200, json=payload))).complete(MESSAGES)

        assert result.finish_reason == "tool_calls"
        assert result.tool_calls == (ToolCall("call_9", "log_expense", '{"amount":"250"}'),)

    async def test_truncated_reply_reports_length(self) -> None:
        result = await make_provider(Scripted(httpx.Response(200, json=completion("Half a sen", finish_reason="length")))).complete(MESSAGES)

        assert result.finish_reason == "length"


class TestRetries:
    async def test_retries_rate_limit_then_succeeds(self) -> None:
        delays: list[float] = []
        server = Scripted(httpx.Response(429, json={"error": {"message": "slow down"}}), httpx.Response(200, json=completion()))

        result = await make_provider(server, delays).complete(MESSAGES)

        assert result.content == "Hello!"
        assert result.attempts == 2
        assert len(delays) == 1 and 0 <= delays[0] <= 1

    async def test_honours_retry_after(self) -> None:
        delays: list[float] = []
        server = Scripted(httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json=completion()))

        await make_provider(server, delays).complete(MESSAGES)

        assert delays == [7.0]

    async def test_retries_timeouts_and_5xx_then_gives_up(self) -> None:
        delays: list[float] = []
        server = Scripted(
            httpx.ReadTimeout("slow"),
            httpx.Response(503, json={"error": {"message": "overloaded"}}),
            httpx.Response(502),
        )

        with pytest.raises(LLMUnavailableError):
            await make_provider(server, delays, max_retries=2).complete(MESSAGES)

        assert len(server.requests) == 3  # 1 attempt + 2 retries, then stop
        assert len(delays) == 2

    @pytest.mark.parametrize(
        ("status", "error_type"),
        [(400, LLMBadRequestError), (401, LLMAuthError), (402, LLMQuotaError), (404, LLMBadRequestError)],
    )
    async def test_does_not_retry_non_retryable_errors(self, status: int, error_type: type[Exception]) -> None:
        server = Scripted(httpx.Response(status, json={"error": {"message": "nope"}}))

        with pytest.raises(error_type):
            await make_provider(server).complete(MESSAGES)

        assert len(server.requests) == 1

    async def test_error_inside_a_200_response_is_an_error(self) -> None:
        server = Scripted(
            httpx.Response(200, json={"error": {"code": 502, "message": "upstream died"}}),
            httpx.Response(200, json=completion()),
        )

        result = await make_provider(server, []).complete(MESSAGES)

        assert result.content == "Hello!"
        assert result.attempts == 2

    async def test_rate_limit_after_all_retries_is_reported(self) -> None:
        server = Scripted(*[httpx.Response(429) for _ in range(3)])

        with pytest.raises(LLMRateLimitError):
            await make_provider(server, []).complete(MESSAGES)


class TestPrivacy:
    async def test_api_key_and_prompt_never_appear_in_errors_or_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        secret_prompt = [ChatMessage(role="user", content="My PIN is 4821")]
        server = Scripted(httpx.Response(401, json={"error": {"message": "Invalid key"}}))

        with pytest.raises(LLMAuthError) as excinfo:
            await make_provider(server).complete(secret_prompt)

        logged = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
        for leak in (API_KEY, "4821"):
            assert leak not in str(excinfo.value)
            assert leak not in logged

    async def test_successful_call_logs_metrics_not_content(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("INFO")
        server = Scripted(httpx.Response(200, json=completion("Your balance is 9,995")))

        await make_provider(server).complete([ChatMessage(role="user", content="My PIN is 4821")])

        [record] = [r for r in caplog.records if r.getMessage() == "llm_call"]
        assert record.__dict__["input_tokens"] == 12 and record.__dict__["cost_usd"] == pytest.approx(0.000108)
        assert "4821" not in str(record.__dict__) and "9,995" not in str(record.__dict__)


class TestFakeProvider:
    async def test_scripted_replies_then_echo(self) -> None:
        fake = FakeProvider()
        fake.reply(tool_calls=[ToolCall("c1", "log_expense", "{}")])

        first = await fake.complete(MESSAGES)
        second = await fake.complete(MESSAGES)

        assert first.finish_reason == "tool_calls"
        assert second.content == "(fake reply) Hi"
        assert len(fake.calls) == 2


def sse_body(*chunks: dict[str, Any] | str, done: bool = True) -> bytes:
    """An OpenAI-style event stream. A str chunk is sent as a raw line (e.g. a ':' comment)."""
    lines = [chunk if isinstance(chunk, str) else f"data: {json.dumps(chunk)}" for chunk in chunks]
    if done:
        lines.append("data: [DONE]")
    return ("\n\n".join(lines) + "\n\n").encode()


def delta(text: str, **extra: Any) -> dict[str, Any]:
    return {"choices": [{"delta": {"content": text, **extra}, "finish_reason": None}]}


def streaming(*chunks: dict[str, Any] | str, done: bool = True) -> httpx.Response:
    return httpx.Response(200, content=sse_body(*chunks, done=done), headers={"content-type": "text/event-stream"})


async def collect(provider: OpenRouterProvider) -> tuple[list[str], Any]:
    texts: list[str] = []
    final = None
    async for event in provider.stream(MESSAGES):
        if isinstance(event, TextDelta):
            texts.append(event.text)
        else:
            final = event.result
    return texts, final


class TestStream:
    async def test_yields_text_as_it_arrives_then_the_full_result(self) -> None:
        server = Scripted(
            streaming(
                ": OPENROUTER PROCESSING",  # keep-alive comment while the model thinks
                {"id": "gen-7", "model": "anthropic/claude-opus-5.5", "choices": [{"delta": {"role": "assistant", "content": ""}}]},
                delta("Hel"),
                delta("lo", reasoning="hidden thoughts"),
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 2, "cost": 0.00004}},
            )
        )

        texts, result = await collect(make_provider(server))

        assert texts == ["Hel", "lo"]
        assert result.content == "Hello"
        assert "hidden" not in result.content  # reasoning tokens are never forwarded
        assert (result.usage.input_tokens, result.usage.output_tokens) == (9, 2)
        assert result.usage.cost_usd == pytest.approx(0.00004)
        assert result.finish_reason == "stop"
        assert result.provider_request_id == "gen-7"
        assert result.time_to_first_token_ms is not None
        body = server.body()
        assert body["stream"] is True and "temperature" not in body

    async def test_retries_before_the_first_token(self) -> None:
        server = Scripted(httpx.Response(503, json={"error": {"message": "busy"}}), streaming(delta("Hi")))

        texts, result = await collect(make_provider(server, []))

        assert texts == ["Hi"] and result.attempts == 2

    async def test_does_not_retry_after_text_was_shown(self) -> None:
        server = Scripted(
            streaming(delta("Half a "), {"error": {"code": 502, "message": "upstream died"}}, done=False),
            streaming(delta("never sent")),
        )
        texts: list[str] = []

        with pytest.raises(LLMUnavailableError):
            async for event in make_provider(server, []).stream(MESSAGES):
                if isinstance(event, TextDelta):
                    texts.append(event.text)

        assert texts == ["Half a "]
        assert len(server.requests) == 1  # a retry would glue a different reply onto this one

    async def test_auth_error_fails_fast(self) -> None:
        server = Scripted(httpx.Response(401, json={"error": {"message": "bad key"}}))

        with pytest.raises(LLMAuthError):
            await collect(make_provider(server))

        assert len(server.requests) == 1

    async def test_logs_time_to_first_token_but_not_content(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level("INFO")
        server = Scripted(streaming(delta("Your PIN is 4821")))

        await collect(make_provider(server))

        [record] = [r for r in caplog.records if r.getMessage() == "llm_call"]
        assert record.__dict__["ttft_ms"] is not None
        assert "4821" not in str(record.__dict__)

    async def test_fake_provider_streams_word_by_word(self) -> None:
        fake = FakeProvider()
        fake.reply("one two three")

        texts = [e.text async for e in fake.stream(MESSAGES) if isinstance(e, TextDelta)]

        assert texts == ["one ", "two ", "three"]
