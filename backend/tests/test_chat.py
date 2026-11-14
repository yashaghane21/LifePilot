"""Chat and conversations: the full turn, user isolation, failure handling, context and privacy."""

import json
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import date
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from app.ai.chat.context import PastMessage, build_messages
from app.ai.chat.router import get_chat_provider
from app.ai.chat.service import drain_background_saves, prepare_turn, stream_chat_turn
from app.ai.prompts.system import PROMPT_VERSION
from app.ai.providers.base import (
    ChatMessage,
    ChatResult,
    LLMBadRequestError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMUnavailableError,
    ResponseSchema,
    StreamDone,
    StreamEvent,
    TextDelta,
    ToolSpec,
    Usage,
)
from app.ai.providers.fake import FakeProvider
from app.db.session import SessionLocal, engine
from app.modules.conversations.models import Conversation, Message
from app.modules.conversations.service import title_from_message
from app.modules.users.models import User
from tests.test_auth import bearer, register, token_for

pytestmark = pytest.mark.usefixtures("clean_db")

TODAY = date(2026, 11, 14)


@pytest.fixture
def fake(app: FastAPI) -> Iterator[FakeProvider]:
    provider = FakeProvider()
    app.dependency_overrides[get_chat_provider] = lambda: provider
    yield provider
    app.dependency_overrides.clear()


async def send(
    client: httpx.AsyncClient, token: str, message: str, conversation_id: str | None = None
) -> httpx.Response:
    body: dict[str, str] = {"message": message}
    if conversation_id:
        body["conversation_id"] = conversation_id
    return await client.post("/api/v1/chat", json=body, headers=bearer(token))


async def count(model: type[Conversation] | type[Message]) -> int:
    async with SessionLocal() as db:
        return await db.scalar(select(func.count()).select_from(model)) or 0


class TestChatTurn:
    async def test_new_conversation_stores_both_messages(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        token = await token_for(client, "a@example.com")
        fake.reply("Hello! How can I help?")

        response = await send(client, token, "  Plan my week  ")

        assert response.status_code == 200
        body = response.json()
        assert body["conversation"]["title"] == "Plan my week"
        assert body["user_message"]["role"] == "user"
        assert body["user_message"]["content"] == "Plan my week"  # whitespace stripped
        assert body["user_message"]["model"] is None
        reply = body["assistant_message"]
        assert reply["content"] == "Hello! How can I help?"
        assert (reply["model"], reply["input_tokens"], reply["output_tokens"]) == ("fake-model", 10, 5)
        assert reply["cost_usd"] == "0.00000000"  # money is a fixed-point decimal string, never a JSON float
        assert await count(Message) == 2

    async def test_assistant_message_records_prompt_version(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        token = await token_for(client, "a@example.com")

        await send(client, token, "Hi")

        async with SessionLocal() as db:
            versions = list(await db.scalars(select(Message.prompt_version).where(Message.role == "assistant")))
        assert versions == [PROMPT_VERSION]

    async def test_follow_up_sends_history_in_order(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        token = await token_for(client, "a@example.com")
        fake.reply("Sure, what's the date?")
        first = (await send(client, token, "Remind me about rent")).json()

        await send(client, token, "The 5th", first["conversation"]["id"])

        sent = fake.calls[1].messages
        assert [m.role for m in sent] == ["system", "user", "assistant", "user"]
        assert [m.content for m in sent[1:]] == ["Remind me about rent", "Sure, what's the date?", "The 5th"]

    async def test_follow_up_moves_conversation_to_top(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        token = await token_for(client, "a@example.com")
        older = (await send(client, token, "First topic")).json()["conversation"]["id"]
        await send(client, token, "Second topic")

        await send(client, token, "Back to the first", older)

        listed = (await client.get("/api/v1/conversations", headers=bearer(token))).json()
        assert [c["id"] for c in listed][0] == older

    async def test_get_conversation_returns_messages_in_order(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        token = await token_for(client, "a@example.com")
        conversation_id = (await send(client, token, "one")).json()["conversation"]["id"]
        await send(client, token, "two", conversation_id)

        response = await client.get(f"/api/v1/conversations/{conversation_id}", headers=bearer(token))

        assert response.status_code == 200
        # Read back from NUMERIC: same fixed-point string as the POST returned (not "0E-8").
        assert response.json()["messages"][1]["cost_usd"] == "0.00000000"
        assert [(m["role"], m["content"]) for m in response.json()["messages"]] == [
            ("user", "one"),
            ("assistant", "(fake reply) one"),
            ("user", "two"),
            ("assistant", "(fake reply) two"),
        ]

    async def test_delete_removes_conversation_and_messages(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        token = await token_for(client, "a@example.com")
        conversation_id = (await send(client, token, "temporary")).json()["conversation"]["id"]

        response = await client.delete(f"/api/v1/conversations/{conversation_id}", headers=bearer(token))

        assert response.status_code == 204
        assert (await count(Conversation), await count(Message)) == (0, 0)


class TestIsolation:
    """User B must not be able to read, continue or delete user A's conversation."""

    async def make_two_users(self, client: httpx.AsyncClient) -> tuple[str, str, str]:
        alice = await token_for(client, "alice@example.com")
        bob = await token_for(client, "bob@example.com")
        conversation_id = (await send(client, alice, "my private note")).json()["conversation"]["id"]
        return alice, bob, conversation_id

    async def test_cannot_read_anothers_conversation(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        _, bob, conversation_id = await self.make_two_users(client)

        response = await client.get(f"/api/v1/conversations/{conversation_id}", headers=bearer(bob))

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "conversation_not_found"
        assert "private note" not in response.text

    async def test_cannot_continue_anothers_conversation(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        _, bob, conversation_id = await self.make_two_users(client)
        calls_before = len(fake.calls)

        response = await send(client, bob, "hijack", conversation_id)

        assert response.status_code == 404
        assert len(fake.calls) == calls_before  # rejected before any tokens were spent
        assert await count(Message) == 2

    async def test_cannot_delete_anothers_conversation(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        _, bob, conversation_id = await self.make_two_users(client)

        response = await client.delete(f"/api/v1/conversations/{conversation_id}", headers=bearer(bob))

        assert response.status_code == 404
        assert await count(Conversation) == 1

    async def test_list_shows_only_own_conversations(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        alice, bob, conversation_id = await self.make_two_users(client)
        await send(client, bob, "bob's topic")

        alice_list = (await client.get("/api/v1/conversations", headers=bearer(alice))).json()
        bob_list = (await client.get("/api/v1/conversations", headers=bearer(bob))).json()

        assert [c["id"] for c in alice_list] == [conversation_id]
        assert [c["title"] for c in bob_list] == ["bob's topic"]

    async def test_unknown_id_looks_the_same_as_anothers(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        _, bob, conversation_id = await self.make_two_users(client)

        theirs = await client.get(f"/api/v1/conversations/{conversation_id}", headers=bearer(bob))
        missing = await client.get(f"/api/v1/conversations/{uuid.uuid7()}", headers=bearer(bob))

        assert theirs.status_code == missing.status_code == 404
        assert theirs.json()["error"]["message"] == missing.json()["error"]["message"]

    @pytest.mark.parametrize(
        ("method", "path"),
        [("GET", "/api/v1/conversations"), ("GET", f"/api/v1/conversations/{uuid.UUID(int=1)}"), ("POST", "/api/v1/chat")],
    )
    async def test_requires_authentication(self, client: httpx.AsyncClient, method: str, path: str) -> None:
        response = await client.request(method, path, json={"message": "hi"})

        assert response.status_code == 401


class TestValidation:
    @pytest.mark.parametrize("message", ["", "   \n ", "x" * 8001])
    async def test_rejects_empty_or_oversized_messages(
        self, client: httpx.AsyncClient, fake: FakeProvider, message: str
    ) -> None:
        token = await token_for(client, "a@example.com")

        response = await send(client, token, message)

        assert response.status_code == 422
        assert fake.calls == []


class TestFailures:
    """A failed model call must leave nothing behind: no half-saved turn, no empty conversation."""

    @pytest.mark.parametrize(
        ("error", "status", "code"),
        [
            (LLMRateLimitError("slow down"), 503, "assistant_unavailable"),
            (LLMUnavailableError("timeout"), 503, "assistant_unavailable"),
            (LLMQuotaError("no credit"), 502, "assistant_failed"),
            (LLMBadRequestError("unknown model"), 502, "assistant_failed"),
        ],
    )
    async def test_llm_error_stores_nothing(
        self, client: httpx.AsyncClient, app: FastAPI, error: Exception, status: int, code: str
    ) -> None:
        token = await token_for(client, "a@example.com")
        app.dependency_overrides[get_chat_provider] = lambda: FailingProvider(error)

        response = await send(client, token, "hello")

        assert response.status_code == status
        assert response.json()["error"]["code"] == code
        assert "slow down" not in response.text and "unknown model" not in response.text  # no provider internals
        assert (await count(Conversation), await count(Message)) == (0, 0)

    @pytest.mark.parametrize("content", [None, "", "   "])
    async def test_empty_reply_is_rejected_and_not_stored(
        self, client: httpx.AsyncClient, fake: FakeProvider, content: str | None
    ) -> None:
        token = await token_for(client, "a@example.com")
        fake.reply(content)

        response = await send(client, token, "hello")

        assert response.status_code == 502
        assert await count(Message) == 0

    async def test_db_connection_is_released_during_the_llm_call(self, client: httpx.AsyncClient, app: FastAPI) -> None:
        token = await token_for(client, "a@example.com")
        spy = PoolSpyProvider()
        app.dependency_overrides[get_chat_provider] = lambda: spy
        conversation_id = (await send(client, token, "first")).json()["conversation"]["id"]

        await send(client, token, "second", conversation_id)  # this turn reads history first

        assert spy.checked_out == [0, 0]


class TestPrivacy:
    async def test_profile_data_is_not_sent_to_the_provider(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        await register(client, email="priya.sharma@example.com", full_name="Priya Sharma")
        token = (
            await client.post(
                "/api/v1/auth/login", json={"email": "priya.sharma@example.com", "password": "correct horse battery staple"}
            )
        ).json()["access_token"]

        await send(client, token, "hello")

        sent = " ".join(m.content or "" for m in fake.calls[0].messages)
        assert "priya" not in sent.lower() and "sharma" not in sent.lower()

    async def test_message_content_is_not_logged(
        self, client: httpx.AsyncClient, fake: FakeProvider, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level("DEBUG")
        token = await token_for(client, "a@example.com")
        fake.reply("Your PIN is safe with me")

        await send(client, token, "my PIN is 4821")

        logged = " ".join(f"{r.getMessage()} {r.__dict__}" for r in caplog.records)
        assert "chat_turn" in logged
        assert "4821" not in logged and "safe with me" not in logged


class TestContext:
    def past(self, *pairs: tuple[str, str]) -> list[PastMessage]:
        return [PastMessage(role=role, content=content) for role, content in pairs]  # type: ignore[arg-type]

    def test_system_prompt_first_then_history_then_new_message(self) -> None:
        messages = build_messages(self.past(("user", "a"), ("assistant", "b")), "c", today=TODAY)

        assert messages[0].role == "system"
        assert "2026-11-14" in (messages[0].content or "")
        assert [(m.role, m.content) for m in messages[1:]] == [("user", "a"), ("assistant", "b"), ("user", "c")]

    def test_keeps_only_the_newest_messages(self) -> None:
        history = self.past(*[("user" if i % 2 == 0 else "assistant", str(i)) for i in range(30)])

        messages = build_messages(history, "new", today=TODAY, max_messages=4)

        assert [m.content for m in messages[1:]] == ["26", "27", "28", "29", "new"]

    def test_character_budget_drops_oldest_first(self) -> None:
        history = self.past(("user", "x" * 50), ("assistant", "y" * 50), ("user", "z" * 50), ("assistant", "w" * 50))

        messages = build_messages(history, "new", today=TODAY, max_chars=120)

        assert [m.content for m in messages[1:]] == ["z" * 50, "w" * 50, "new"]

    def test_never_starts_with_an_orphaned_assistant_reply(self) -> None:
        history = self.past(("user", "q1"), ("assistant", "a1"), ("user", "q2"), ("assistant", "a2"))

        messages = build_messages(history, "new", today=TODAY, max_messages=3)

        assert [m.content for m in messages[1:]] == ["q2", "a2", "new"]

    def test_title_is_trimmed_and_collapsed(self) -> None:
        assert title_from_message("  hello \n  world ") == "hello world"
        long_title = title_from_message("word " * 40)
        assert len(long_title) <= 60 and long_title.endswith("…")


class FailingProvider(FakeProvider):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def complete(self, messages: Sequence[ChatMessage], **kwargs: object) -> ChatResult:  # type: ignore[override]
        raise self.error


class PoolSpyProvider(FakeProvider):
    """Records how many pooled DB connections are checked out while the model is 'thinking'."""

    def __init__(self) -> None:
        super().__init__()
        self.checked_out: list[int] = []

    async def complete(  # type: ignore[override]
        self,
        messages: Sequence[ChatMessage],
        *,
        model: str | None = None,
        tools: Sequence[ToolSpec] = (),
        response_schema: ResponseSchema | None = None,
        max_output_tokens: int = 4096,
    ) -> ChatResult:
        self.checked_out.append(engine.pool.checkedout())  # type: ignore[attr-defined]
        return ChatResult("ok", (), "stop", Usage(1, 1, None), "fake-model", 1.0)


# ------------------------------------------------------------------ streaming


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


async def stream(
    client: httpx.AsyncClient, token: str, message: str, conversation_id: str | None = None
) -> httpx.Response:
    body: dict[str, str] = {"message": message}
    if conversation_id:
        body["conversation_id"] = conversation_id
    return await client.post("/api/v1/chat/stream", json=body, headers=bearer(token))


class MidStreamFailure(FakeProvider):
    async def stream(self, messages: Sequence[ChatMessage], **kwargs: object) -> AsyncIterator[StreamEvent]:  # type: ignore[override]
        yield TextDelta("Half an ")
        raise LLMUnavailableError("connection dropped")


class PoolSpyStreamProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.checked_out: list[int] = []

    async def stream(self, messages: Sequence[ChatMessage], **kwargs: object) -> AsyncIterator[StreamEvent]:  # type: ignore[override]
        self.checked_out.append(engine.pool.checkedout())  # type: ignore[attr-defined]
        yield TextDelta("ok")
        yield StreamDone(ChatResult("ok", (), "stop", Usage(1, 1, None), "fake-model", 1.0))


class TestStreaming:
    async def test_new_conversation_streams_then_stores(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        token = await token_for(client, "a@example.com")
        fake.reply("Here is your weekly plan")

        response = await stream(client, token, "Plan my week")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        events = parse_sse(response.text)
        names = [name for name, _ in events]
        assert names[0] == "start" and names[-1] == "done"
        assert set(names[1:-1]) == {"delta"}
        assert "".join(data["text"] for name, data in events if name == "delta") == "Here is your weekly plan"
        start, done = events[0][1], events[-1][1]
        assert start == {"conversation_id": done["conversation"]["id"], "title": "Plan my week"}
        assert done["assistant_message"]["content"] == "Here is your weekly plan"
        assert await count(Message) == 2

    async def test_follow_up_streams_with_history(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        token = await token_for(client, "a@example.com")
        conversation_id = parse_sse((await stream(client, token, "first")).text)[0][1]["conversation_id"]

        response = await stream(client, token, "second", conversation_id)

        assert parse_sse(response.text)[-1][0] == "done"
        assert [m.content for m in fake.calls[1].messages[1:]] == ["first", "(fake reply) first", "second"]

    async def test_anothers_conversation_is_a_plain_404_before_streaming(
        self, client: httpx.AsyncClient, fake: FakeProvider
    ) -> None:
        alice = await token_for(client, "alice@example.com")
        bob = await token_for(client, "bob@example.com")
        conversation_id = parse_sse((await stream(client, alice, "private")).text)[0][1]["conversation_id"]
        calls_before = len(fake.calls)

        response = await stream(client, bob, "hijack", conversation_id)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "conversation_not_found"
        assert len(fake.calls) == calls_before

    async def test_error_before_any_text_is_an_error_event(self, client: httpx.AsyncClient, app: FastAPI) -> None:
        token = await token_for(client, "a@example.com")
        app.dependency_overrides[get_chat_provider] = lambda: FailingProvider(LLMRateLimitError("slow down"))

        events = parse_sse((await stream(client, token, "hello")).text)

        assert [name for name, _ in events] == ["start", "error"]
        assert events[1][1]["code"] == "assistant_unavailable"
        assert "slow down" not in json.dumps(events)
        assert (await count(Conversation), await count(Message)) == (0, 0)

    async def test_failure_mid_reply_stores_nothing(self, client: httpx.AsyncClient, app: FastAPI) -> None:
        token = await token_for(client, "a@example.com")
        app.dependency_overrides[get_chat_provider] = MidStreamFailure

        events = parse_sse((await stream(client, token, "hello")).text)

        assert [name for name, _ in events] == ["start", "delta", "error"]
        assert (await count(Conversation), await count(Message)) == (0, 0)

    async def test_empty_reply_is_an_error_event(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        token = await token_for(client, "a@example.com")
        fake.reply("   ")

        events = parse_sse((await stream(client, token, "hello")).text)

        assert events[-1][0] == "error" and events[-1][1]["code"] == "assistant_failed"
        assert await count(Message) == 0

    async def test_no_db_connection_is_held_while_streaming(self, client: httpx.AsyncClient, app: FastAPI) -> None:
        token = await token_for(client, "a@example.com")
        spy = PoolSpyStreamProvider()
        app.dependency_overrides[get_chat_provider] = lambda: spy
        conversation_id = parse_sse((await stream(client, token, "first")).text)[0][1]["conversation_id"]

        await stream(client, token, "second", conversation_id)

        assert spy.checked_out == [0, 0]


class TestStop:
    """Closing the stream mid-reply (Stop button, closed tab) keeps the text already shown."""

    async def start_stream(self, client: httpx.AsyncClient, fake: FakeProvider) -> AsyncIterator[str]:
        await register(client, email="a@example.com")
        async with SessionLocal() as db:
            user_id = (await db.scalars(select(User.id).where(User.email == "a@example.com"))).one()
            turn = await prepare_turn(db, user_id=user_id, conversation_id=None, text="Tell me a story", today=TODAY)
        fake.reply("Once upon a time there was a cat")
        return stream_chat_turn(fake, turn)

    async def test_stopped_reply_is_saved_as_cancelled(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        events = await self.start_stream(client, fake)
        received = [await anext(events) for _ in range(3)]  # start + two words

        await events.aclose()  # what the server does when the client disconnects
        await drain_background_saves()

        assert received[0].startswith("event: start")
        async with SessionLocal() as db:
            messages = list(await db.scalars(select(Message).order_by(Message.created_at, Message.id)))
        assert [(m.role, m.content) for m in messages] == [("user", "Tell me a story"), ("assistant", "Once upon")]
        stopped = messages[1]
        assert stopped.finish_reason == "cancelled"
        assert stopped.input_tokens is None and stopped.cost_usd is None  # usage only arrives at the end

    async def test_stop_before_any_text_saves_nothing(self, client: httpx.AsyncClient, fake: FakeProvider) -> None:
        events = await self.start_stream(client, fake)
        await anext(events)  # only the start event

        await events.aclose()
        await drain_background_saves()

        assert (await count(Conversation), await count(Message)) == (0, 0)
