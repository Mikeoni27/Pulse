from fastapi import APIRouter

from app.api.v1 import attribution, auth, links, stats, webhooks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(links.router)
api_router.include_router(stats.router)
api_router.include_router(webhooks.router)
api_router.include_router(attribution.router)