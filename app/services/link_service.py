import secrets
import string
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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

    # Custom code path
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

    # Random code path — retry on collision
    for _ in range(MAX_GENERATION_ATTEMPTS):
        code = generate_short_code()
        link = Link(short_code=code, target_url=target, owner_id=owner_id)
        db.add(link)
        try:
            await db.commit()
            await db.refresh(link)
            return link
        except IntegrityError:
            # Collision on the unique constraint — rollback and retry
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