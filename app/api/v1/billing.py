from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.config import settings
from app.db.models.user import User
from app.db.session import get_db
from app.services import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    tier: str  # "pro" or "business"


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    payload: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Start a Stripe Checkout session for upgrading to a paid tier."""
    if payload.tier == "pro":
        price_id = settings.STRIPE_PRICE_PRO
    elif payload.tier == "business":
        price_id = settings.STRIPE_PRICE_BUSINESS
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tier. Must be 'pro' or 'business'.",
        )

    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Price not configured for this tier",
        )

    base_url = settings.BASE_URL.rstrip("/")
    try:
        url = await billing_service.create_checkout_session(
            db,
            current_user,
            price_id=price_id,
            success_url=f"{base_url}/dashboard?upgraded=1",
            cancel_url=f"{base_url}/pricing?canceled=1",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create checkout session: {e}",
        )

    return {"url": url}


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Open the Stripe Customer Portal to manage the subscription."""
    base_url = settings.BASE_URL.rstrip("/")
    try:
        url = await billing_service.create_portal_session(
            db,
            current_user,
            return_url=f"{base_url}/dashboard",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create portal session: {e}",
        )

    return {"url": url}