from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.stats import LinkStats
from app.services import link_service

router = APIRouter(prefix="/links", tags=["stats"])


@router.get("/{short_code}/stats", response_model=LinkStats)
async def get_stats(
    short_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    link = await link_service.get_link_owner_check(db, short_code, current_user.id)
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found or does not belong to you",
        )
    return await link_service.get_link_stats(db, link)