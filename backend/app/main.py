from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.ai.chat.router import router as chat_router
from app.ai.providers.factory import close_llm_provider
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import request_context_middleware
from app.db.session import engine
from app.modules.auth.google_router import router as google_auth_router
from app.modules.auth.router import router as auth_router
from app.modules.conversations.router import router as conversations_router
from app.modules.health.router import router as health_router
from app.modules.users.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    # Close pooled connections cleanly on shutdown.
    await close_llm_provider()
    await engine.dispose()


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)

    app = FastAPI(title="LifePilot AI", version="0.1.0", lifespan=lifespan)
    app.middleware("http")(request_context_middleware)
    register_exception_handlers(app)

    # Health checks stay unversioned at the root; everything else lives under /api/v1.
    app.include_router(health_router)
    api = APIRouter(prefix="/api/v1")
    api.include_router(auth_router)
    api.include_router(google_auth_router)
    api.include_router(users_router)
    api.include_router(conversations_router)
    api.include_router(chat_router)
    app.include_router(api)
    return app


app = create_app()
