from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    clear_auth_cookie,
    create_access_token,
    decode_access_token,
    hash_password,
    set_auth_cookie,
    verify_password,
)
from app.core.templates import templates
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter(tags=["ui"])


async def get_optional_user(request: Request, db: AsyncSession) -> User | None:
    """Read JWT from cookie, return User if valid, else None."""
    from app.core.security import COOKIE_NAME

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
    except Exception:
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_optional_user(request, db)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "current_user": user},
    )


@router.get("/pricing", response_class=HTMLResponse)
async def pricing_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_optional_user(request, db)
    return templates.TemplateResponse(
        "pricing.html",
        {"request": request, "current_user": user},
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_optional_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "current_user": None},
    )


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "current_user": None, "error": "Invalid email or password"},
            status_code=400,
        )

    token = create_access_token(subject=user.id)
    response = RedirectResponse(url="/dashboard", status_code=303)
    set_auth_cookie(response, token)
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_optional_user(request, db)
    if user:
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "current_user": None},
    )


@router.post("/register")
async def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "current_user": None, "error": "Email already registered"},
            status_code=400,
        )

    if len(password) < 8:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "current_user": None, "error": "Password must be at least 8 characters"},
            status_code=400,
        )

    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(subject=user.id)
    response = RedirectResponse(url="/dashboard", status_code=303)
    set_auth_cookie(response, token)
    return response


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=303)
    clear_auth_cookie(response)
    return response


# ---------- Dashboard ----------


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user = await get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    from app.services import attribution_service, link_service

    links = await link_service.list_links(db, owner_id=user.id, limit=50)
    summary = await attribution_service.get_attribution_summary(db, user.id)

    revenue_by_code = {item["short_code"]: item for item in summary["top_links"]}

    enriched = []
    for link in links:
        rev = revenue_by_code.get(link.short_code, {})
        enriched.append({
            "short_code": link.short_code,
            "target_url": link.target_url,
            "click_count": link.click_count,
            "is_active": link.is_active,
            "created_at": link.created_at,
            "revenue_cents": rev.get("total_revenue_cents", 0),
            "conversions": rev.get("total_conversions", 0),
        })

    total_clicks = sum(l["click_count"] for l in enriched)
    total_revenue_cents = summary["total_revenue_cents"]

    error_msg = None
    error_code = request.query_params.get("error")
    if error_code == "invalid_url":
        error_msg = "Invalid URL. Please enter a valid https:// URL."
    elif error_code == "code_taken":
        error_msg = "That custom code is already taken. Try another one."
    elif error_code == "unknown":
        error_msg = "Something went wrong. Please try again."
    elif error_code == "not_found":
        error_msg = "Link not found or does not belong to you."

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_user": user,
            "links": enriched,
            "total_links": len(enriched),
            "total_clicks": total_clicks,
            "total_revenue_cents": total_revenue_cents,
            "total_conversions": summary["total_conversions"],
            "error": error_msg,
        },
    )


@router.post("/dashboard/links")
async def create_link_ui(
    request: Request,
    target_url: str = Form(...),
    custom_code: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    user = await get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    from app.schemas.link import LinkCreate
    from app.services import link_service

    try:
        payload = LinkCreate(
            target_url=target_url,
            custom_code=custom_code.strip() or None,
        )
    except Exception:
        return RedirectResponse(url="/dashboard?error=invalid_url", status_code=303)

    try:
        await link_service.create_link(db, payload, owner_id=user.id)
    except ValueError:
        return RedirectResponse(url="/dashboard?error=code_taken", status_code=303)
    except Exception:
        return RedirectResponse(url="/dashboard?error=unknown", status_code=303)

    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/dashboard/links/{short_code}", response_class=HTMLResponse)
async def link_detail(
    short_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await get_optional_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    from app.services import attribution_service, link_service

    # Fetch the link — enforce ownership
    link = await link_service.get_link_owner_check(db, short_code, user.id)
    if not link:
        return RedirectResponse(url="/dashboard?error=not_found", status_code=303)

    # Get click stats
    stats = await link_service.get_link_stats(db, link)

    # Get revenue for this specific link
    revenue_items = await attribution_service.get_revenue_by_link(db, user.id, limit=100)
    revenue = next(
        (r for r in revenue_items if r["short_code"] == short_code),
        {"total_conversions": 0, "total_revenue_cents": 0, "currency": "usd"},
    )

    return templates.TemplateResponse(
        "link_detail.html",
        {
            "request": request,
            "current_user": user,
            "link": link,
            "stats": stats,
            "revenue": revenue,
        },
    )