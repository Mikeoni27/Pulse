from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from sqlalchemy import text

from app.api.v1.redirect import router as redirect_router
from app.api.v1.router import api_router
from app.api.views import router as views_router
from app.core.config import settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Shutdown: close the Redis connection cleanly
    from app.services.cache_service import get_redis

    try:
        redis = get_redis()
        await redis.aclose()
    except Exception:
        pass


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)


@app.middleware("http")
async def no_cache_html(request: Request, call_next):
    """Prevent browser caching of HTML so auth state refreshes correctly."""
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


# Order matters: views_router owns "/", so include it last
# to give API + redirect routers priority on their paths.
app.include_router(api_router)
app.include_router(redirect_router)
app.include_router(views_router)


@app.get("/health", tags=["health"])
async def health() -> dict:
    db_ok = False
    redis_ok = False

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        redis_ok = True
    except Exception:
        redis_ok = False

    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "database": "up" if db_ok else "down",
        "redis": "up" if redis_ok else "down",
    }