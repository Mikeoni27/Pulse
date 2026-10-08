import secrets
import string
import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.click import Click
from app.db.models.link import Link
from app.schemas.link import LinkCreate

ALPHABET = string.ascii_letters + string.digits  # base62
CODE_LENGTH = 7
MAX_GENERATION_ATTEMPTS = 5


def generate_short_code(length: int = CODE_LENGTH) -> str:
    """Generate a cryptographically random base62 short code.

    7 chars of base62 = 62^7 ≈ 3.5 trillion possibilities.
    Birthday-paradox collision becomes relevant around ~60M codes.
    """
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


async def get_link_by_code(db: AsyncSession, short_code: str) -> Link | None:
    result = await db.execute(select(Link).where(Link.short_code == short_code))
    return result.scalar_one_or_none()


async def get_link_by_code_cached(db: AsyncSession, short_code: str) -> Link | None:
    """Look up a link by code, checking Redis first.

    On cache hit, returns a Link object populated from the cached dict
    (without hitting the DB). On miss, queries the DB and warms the cache.
    """
    from app.services import cache_service

    key = cache_service.link_cache_key(short_code)
    cached = await cache_service.cache_get(key)

    if cached is not None:
        link = Link(
            id=uuid.UUID(cached["id"]),
            short_code=cached["short_code"],
            target_url=cached["target_url"],
            is_active=cached["is_active"],
            click_count=cached.get("click_count", 0),
        )
        return link

    link = await get_link_by_code(db, short_code)
    if link is None:
        return None

    await cache_service.cache_set(
        key,
        {
            "id": str(link.id),
            "short_code": link.short_code,
            "target_url": link.target_url,
            "is_active": link.is_active,
            "click_count": link.click_count,
        },
    )
    return link


async def create_link(
    db: AsyncSession,
    payload: LinkCreate,
    owner_id: uuid.UUID | None = None,
) -> Link:
    """Create a new short link. Handles custom codes and collision-safe random codes.

    Raises:
        ValueError: if a requested custom_code is already taken.
    """
    target = str(payload.target_url)

    if payload.custom_code:
        existing = await get_link_by_code(db, payload.custom_code)
        if existing:
            raise ValueError(f"Custom code '{payload.custom_code}' is already taken")

        link = Link(
            short_code=payload.custom_code,
            target_url=target,
            owner_id=owner_id,
        )
        db.add(link)
        await db.commit()
        await db.refresh(link)
        return link

    for _ in range(MAX_GENERATION_ATTEMPTS):
        code = generate_short_code()
        link = Link(short_code=code, target_url=target, owner_id=owner_id)
        db.add(link)
        try:
            await db.commit()
            await db.refresh(link)
            return link
        except IntegrityError:
            await db.rollback()
            continue

    raise RuntimeError("Failed to generate a unique short code after multiple attempts")


async def list_links(
    db: AsyncSession,
    owner_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Link]:
    stmt = select(Link).order_by(Link.created_at.desc()).offset(skip).limit(limit)
    if owner_id is not None:
        stmt = stmt.where(Link.owner_id == owner_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def record_click(
    db: AsyncSession,
    link: Link,
    ip_address: str | None,
    user_agent: str | None,
    referrer: str | None,
) -> uuid.UUID:
    """Record a click, increment the counter, and return the click's ID.

    Synchronous version. Used as a fallback if the async queue is unavailable.
    Returns the click UUID for attribution purposes.
    """
    click = Click(
        link_id=link.id,
        ip_address=ip_address,
        user_agent=user_agent,
        referrer=referrer,
    )
    db.add(click)

    await db.execute(
        update(Link)
        .where(Link.id == link.id)
        .values(click_count=Link.click_count + 1)
    )
    await db.commit()
    await db.refresh(click)
    return click.id


async def enqueue_click(
    link: Link,
    ip_address: str | None,
    user_agent: str | None,
    referrer: str | None,
) -> uuid.UUID:
    """Push a click event onto the Arq queue for async processing.

    Returns the pre-generated click_id — the worker will insert a Click row
    with this exact ID, so we can reference it in the redirect URL immediately
    (without waiting for the worker to finish).

    Falls back to a synchronous DB write if Redis is unavailable.
    """
    from arq import create_pool

    from app.workers.settings import redis_settings

    click_id = uuid.uuid4()

    try:
        redis = await create_pool(redis_settings())
        await redis.enqueue_job(
            "record_click_task",
            click_id=str(click_id),
            link_id=str(link.id),
            ip_address=ip_address,
            user_agent=user_agent,
            referrer=referrer,
        )
        await redis.aclose()
        return click_id
    except Exception:
        # Fallback: sync write so we don't lose the click
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            return await record_click(
                db,
                link,
                ip_address=ip_address,
                user_agent=user_agent,
                referrer=referrer,
            )

async def get_link_owner_check(
    db: AsyncSession, short_code: str, owner_id: uuid.UUID
) -> Link | None:
    """Fetch a link only if it belongs to the given owner.

    Used for the stats endpoint — users can only see their own analytics.
    """
    result = await db.execute(
        select(Link).where(Link.short_code == short_code, Link.owner_id == owner_id)
    )
    return result.scalar_one_or_none()


async def get_link_stats(db: AsyncSession, link: Link) -> dict:
    """Aggregate analytics for a link.

    Returns a dict ready to be passed to a Pydantic response schema.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import desc, func

    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    total_stmt = select(func.count(Click.id)).where(Click.link_id == link.id)
    total = (await db.execute(total_stmt)).scalar_one()

    last_24h_stmt = select(func.count(Click.id)).where(
        Click.link_id == link.id, Click.created_at >= last_24h
    )
    last_24h_count = (await db.execute(last_24h_stmt)).scalar_one()

    last_7d_stmt = select(func.count(Click.id)).where(
        Click.link_id == link.id, Click.created_at >= last_7d
    )
    last_7d_count = (await db.execute(last_7d_stmt)).scalar_one()

    top_referrers_stmt = (
        select(Click.referrer, func.count(Click.id).label("count"))
        .where(Click.link_id == link.id, Click.created_at >= last_7d)
        .group_by(Click.referrer)
        .order_by(desc("count"))
        .limit(5)
    )
    top_referrers = [
        {"referrer": row.referrer, "count": row.count}
        for row in (await db.execute(top_referrers_stmt)).all()
    ]

    top_user_agents_stmt = (
        select(Click.user_agent, func.count(Click.id).label("count"))
        .where(Click.link_id == link.id, Click.created_at >= last_7d)
        .group_by(Click.user_agent)
        .order_by(desc("count"))
        .limit(5)
    )
    top_user_agents = [
        {"user_agent": row.user_agent, "count": row.count}
        for row in (await db.execute(top_user_agents_stmt)).all()
    ]

    return {
        "short_code": link.short_code,
        "target_url": link.target_url,
        "total_clicks": total,
        "clicks_last_24h": last_24h_count,
        "clicks_last_7d": last_7d_count,
        "top_referrers": top_referrers,
        "top_user_agents": top_user_agents,
    }