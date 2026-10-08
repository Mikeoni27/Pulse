from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.conversion import AttributionSummary
from app.services import attribution_service

router = APIRouter(prefix="/attribution", tags=["attribution"])


@router.get("/summary", response_model=AttributionSummary)
async def get_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Overall revenue attribution for the current user."""
    return await attribution_service.get_attribution_summary(db, current_user.id)