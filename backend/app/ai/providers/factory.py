"""The one place that decides which LLM provider the app talks to."""

from functools import cache

from app.ai.providers.base import LLMAuthError, LLMProvider
from app.ai.providers.fake import FakeProvider
from app.ai.providers.openrouter import OpenRouterProvider
from app.core.config import get_settings


@cache
def get_llm_provider() -> LLMProvider:
    """Process-wide provider (it owns a pooled HTTP client). Use as a FastAPI dependency."""
    settings = get_settings()
    if settings.llm_provider == "fake":
        return FakeProvider()
    if settings.openrouter_api_key is None:
        raise LLMAuthError("OPENROUTER_API_KEY is not set")
    return OpenRouterProvider(
        api_key=settings.openrouter_api_key.get_secret_value(),
        default_model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        app_url=settings.web_app_url,
    )


async def close_llm_provider() -> None:
    """Called on app shutdown to close the provider's connection pool."""
    if get_llm_provider.cache_info().currsize:
        await get_llm_provider().aclose()
        get_llm_provider.cache_clear()
