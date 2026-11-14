import re

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.errors import AppError
from app.core.middleware import REQUEST_ID_HEADER


class _Expense(BaseModel):
    amount: float
    note: str


class _QuotaExceededError(AppError):
    status_code = 429
    code = "quota_exceeded"


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    """The default app plus throwaway routes that trigger each error path."""

    @app.get("/_test/crash")
    async def crash() -> None:
        raise RuntimeError("internal detail: SELECT * FROM users")

    @app.post("/_test/expense")
    async def create_expense(expense: _Expense) -> _Expense:
        return expense

    @app.get("/_test/app-error")
    async def app_error() -> None:
        raise _QuotaExceededError("Daily limit reached")

    return app


class TestRequestId:
    async def test_generated_when_absent(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health")

        assert re.fullmatch(r"[0-9a-f]{32}", response.headers[REQUEST_ID_HEADER])

    async def test_client_value_is_echoed(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/health", headers={REQUEST_ID_HEADER: "trace-abc-123"})

        assert response.headers[REQUEST_ID_HEADER] == "trace-abc-123"

    async def test_unsafe_client_value_is_replaced(self, client: httpx.AsyncClient) -> None:
        injected = 'x"}\n{"level":"FAKE'

        response = await client.get("/health", headers={REQUEST_ID_HEADER: injected})

        assert response.headers[REQUEST_ID_HEADER] != injected
        assert re.fullmatch(r"[0-9a-f]{32}", response.headers[REQUEST_ID_HEADER])


class TestErrorFormat:
    async def test_unknown_route(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/does-not-exist", headers={REQUEST_ID_HEADER: "rid-404"})

        assert response.status_code == 404
        assert response.json() == {
            "error": {"code": "not_found", "message": "Not Found", "request_id": "rid-404"}
        }

    async def test_app_error_uses_its_status_and_code(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/_test/app-error")

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "quota_exceeded"
        assert response.json()["error"]["message"] == "Daily limit reached"

    async def test_validation_error_lists_fields_but_not_input(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/_test/expense", json={"amount": "lots", "note": "gave money to Rutu"}
        )

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert [d["loc"] for d in error["details"]] == [["body", "amount"]]
        assert "Rutu" not in response.text
        assert "lots" not in response.text

    async def test_unhandled_exception_is_generic_500(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/_test/crash", headers={REQUEST_ID_HEADER: "rid-500"})

        assert response.status_code == 500
        assert response.json() == {
            "error": {
                "code": "internal_error",
                "message": "Internal server error",
                "request_id": "rid-500",
            }
        }
        assert "SELECT" not in response.text

    async def test_unhandled_exception_is_logged_with_request_id(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        await client.get("/_test/crash", headers={REQUEST_ID_HEADER: "rid-log"})

        [record] = [r for r in caplog.records if r.getMessage() == "unhandled_exception"]
        assert record.exc_info is not None
        assert "SELECT * FROM users" in str(record.exc_info[1])
