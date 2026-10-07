from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services import link_service

router = APIRouter(tags=["redirect"])


@router.get("/r/{short_code}")
async def redirect(
    short_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    link = await link_service.get_link_by_code_cached(db, short_code)

    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")

    if not link.is_active:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Link is no longer active")

    # Extract request metadata
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    referrer = request.headers.get("referer")

    await link_service.enqueue_click(
        link,
        ip_address=ip_address,
        user_agent=user_agent,
        referrer=referrer,

    )

    return RedirectResponse(url=link.target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)