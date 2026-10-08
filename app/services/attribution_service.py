import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.click import Click
from app.db.models.conversion import Conversion
from app.db.models.link import Link


async def record_conversion(
    db: AsyncSession,
    *,
    click_id: uuid.UUID,
    stripe_session_id: str,
    amount: int,
    currency: str,
    status: str = "paid",
    customer_email: str | None = None,
) -> Conversion | None:
    """Create a Conversion row linking a click to a payment.

    Idempotent: if a Conversion with this stripe_session_id already exists,
    returns None (the caller knows it was a duplicate webhook delivery).

    Raises:
        ValueError: if the referenced click_id does not exist.
    """
    # Verify the click exists and get its link_id (denormalize)
    click_result = await db.execute(select(Click).where(Click.id == click_id))
    click = click_result.scalar_one_or_none()
    if click is None:
        raise ValueError(f"Click {click_id} not found")

    conversion = Conversion(
        click_id=click.id,
        link_id=click.link_id,
        stripe_session_id=stripe_session_id,
        amount=amount,
        currency=currency.lower(),
        status=status,
        customer_email=customer_email,
    )
    db.add(conversion)

    try:
        await db.commit()
    except IntegrityError:
        # Duplicate stripe_session_id — this webhook was already processed
        await db.rollback()
        return None

    await db.refresh(conversion)
    return conversion


async def get_revenue_by_link(
    db: AsyncSession,
    owner_id: uuid.UUID,
    limit: int = 10,
) -> list[dict]:
    """Return top-performing links ranked by total revenue.

    Only counts conversions with status='paid'.
    """
    stmt = (
        select(
            Link.short_code,
            Link.target_url,
            func.count(Conversion.id).label("total_conversions"),
            func.coalesce(func.sum(Conversion.amount), 0).label("total_revenue_cents"),
            func.coalesce(func.max(Conversion.currency), "usd").label("currency"),
        )
        .join(Conversion, Conversion.link_id == Link.id)
        .where(Link.owner_id == owner_id, Conversion.status == "paid")
        .group_by(Link.id, Link.short_code, Link.target_url)
        .order_by(func.sum(Conversion.amount).desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "short_code": row.short_code,
            "target_url": row.target_url,
            "total_conversions": row.total_conversions,
            "total_revenue_cents": int(row.total_revenue_cents),
            "currency": row.currency,
        }
        for row in rows
    ]


async def get_attribution_summary(
    db: AsyncSession,
    owner_id: uuid.UUID,
) -> dict:
    """Aggregate revenue across all of a user's links."""

    totals_stmt = (
        select(
            func.count(Conversion.id).label("total_conversions"),
            func.coalesce(func.sum(Conversion.amount), 0).label("total_revenue_cents"),
            func.coalesce(func.max(Conversion.currency), "usd").label("currency"),
        )
        .join(Link, Link.id == Conversion.link_id)
        .where(Link.owner_id == owner_id, Conversion.status == "paid")
    )
    totals = (await db.execute(totals_stmt)).one()

    top_links = await get_revenue_by_link(db, owner_id, limit=10)

    return {
        "total_conversions": totals.total_conversions,
        "total_revenue_cents": int(totals.total_revenue_cents),
        "currency": totals.currency,
        "top_links": top_links,
    }