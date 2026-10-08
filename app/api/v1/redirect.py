from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services import link_service

router = APIRouter(tags=["redirect"])


def _append_click_id(target_url: str, click_id: str) -> str:
    """Append ?pulse_click_id=<id> to a URL, preserving existing query params."""
    parts = urlsplit(target_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("pulse_click_id", click_id))
    new_query = urlencode(query)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


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

    # Extract request metadata (cf-connecting-ip is set by Cloudflare tunnels)
    ip_address = (
        request.headers.get("cf-connecting-ip")
        or (request.client.host if request.client else None)
    )
    user_agent = request.headers.get("user-agent")
    referrer = request.headers.get("referer")

    # Enqueue the click and get back the pre-generated click_id.
    # The worker will persist a Click row with this exact ID asynchronously.
    click_id = await link_service.enqueue_click(
        link,
        ip_address=ip_address,
        user_agent=user_agent,
        referrer=referrer,
    )

    # Append pulse_click_id to the target URL so downstream (Stripe) can
    # round-trip this back to us via client_reference_id.
    redirect_url = _append_click_id(link.target_url, str(click_id))

    return RedirectResponse(url=redirect_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)