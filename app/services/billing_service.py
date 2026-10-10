import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User

stripe.api_key = settings.STRIPE_SECRET_KEY


async def get_or_create_stripe_customer(db: AsyncSession, user: User) -> str:
    """Return the user's Stripe customer ID, creating one if needed."""
    if user.stripe_customer_id:
        return user.stripe_customer_id

    customer = stripe.Customer.create(
        email=user.email,
        metadata={"user_id": str(user.id)},
    )

    user.stripe_customer_id = customer.id
    await db.commit()
    await db.refresh(user)
    return customer.id


async def create_checkout_session(
    db: AsyncSession,
    user: User,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe Checkout Session and return its URL.

    The user is redirected to this URL to complete payment.
    """
    customer_id = await get_or_create_stripe_customer(db, user)

    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
    )
    return session.url


async def create_portal_session(
    db: AsyncSession,
    user: User,
    return_url: str,
) -> str:
    """Create a Stripe Customer Portal session and return its URL.

    The user is redirected here to manage their subscription.
    """
    customer_id = await get_or_create_stripe_customer(db, user)

    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url