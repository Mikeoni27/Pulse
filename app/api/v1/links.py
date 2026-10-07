import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.db.models.link import Link
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.link import LinkCreate, LinkRead
from app.services import link_service

router = APIRouter(prefix="/links", tags=["links"])


@router.post("", response_model=LinkRead, status_code=status.HTTP_201_CREATED)
async def create_link(
    payload: LinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Link:
    try:
        link = await link_service.create_link(db, payload, owner_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return link


@router.get("", response_model=list[LinkRead])
async def list_my_links(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Link]:
    return await link_service.list_links(
        db, owner_id=current_user.id, skip=skip, limit=limit
    )