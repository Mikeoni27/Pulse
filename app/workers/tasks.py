from uuid import UUID

from sqlalchemy import update

from app.db.models.click import Click
from app.db.models.link import Link
from app.db.session import AsyncSessionLocal


async def record_click_task(
    ctx: dict,
    *,
    click_id: str,
    link_id: str,
    ip_address: str | None,
    user_agent: str | None,
    referrer: str | None,
) -> str:
    """Arq task: persist a click event and increment the counter.

    Uses the pre-generated click_id from the redirect handler so the caller
    can reference this Click row immediately (before the worker runs).
    """
    async with AsyncSessionLocal() as db:
        click = Click(
            id=UUID(click_id),
            link_id=UUID(link_id),
            ip_address=ip_address,
            user_agent=user_agent,
            referrer=referrer,
        )
        db.add(click)

        await db.execute(
            update(Link)
            .where(Link.id == UUID(link_id))
            .values(click_count=Link.click_count + 1)
        )
        await db.commit()

    return "ok"