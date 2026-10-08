import logging
import uuid

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.services import attribution_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive and process Stripe webhook events.

    Critical design:
    - We read the RAW body (Stripe signature verification requires this)
    - We verify the signature — reject requests not from Stripe
    - We process idempotently — duplicate deliveries are no-ops
    - We return 200 quickly so Stripe doesn't retry
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header",
        )

    if not settings.STRIPE_WEBHOOK_SECRET or settings.STRIPE_WEBHOOK_SECRET == "whsec_PLACEHOLDER":
        logger.error("STRIPE_WEBHOOK_SECRET is not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        # Invalid payload
        logger.warning("Stripe webhook: invalid payload")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        # Signature mismatch — someone is spoofing
        logger.warning("Stripe webhook: signature verification failed")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event["type"]
    logger.info("Stripe webhook received: %s (id=%s)", event_type, event["id"])

    # Handle only the event we care about for now
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]

        client_reference_id = session.get("client_reference_id")
        if not client_reference_id:
            # Not a Pulse-tracked payment — ignore gracefully
            logger.info("Stripe webhook: no client_reference_id, skipping")
            return {"received": True, "processed": False, "reason": "no_reference"}

        try:
            click_id = uuid.UUID(client_reference_id)
        except (ValueError, TypeError):
            logger.warning("Stripe webhook: invalid click_id format: %s", client_reference_id)
            return {"received": True, "processed": False, "reason": "invalid_click_id"}

        try:
            conversion = await attribution_service.record_conversion(
                db,
                click_id=click_id,
                stripe_session_id=session["id"],
                amount=session.get("amount_total", 0),
                currency=session.get("currency", "usd"),
                status="paid",
                customer_email=session.get("customer_details", {}).get("email"),
            )
        except ValueError as e:
            logger.warning("Stripe webhook: %s", e)
            return {"received": True, "processed": False, "reason": "click_not_found"}

        if conversion is None:
            # Duplicate — already processed
            logger.info("Stripe webhook: duplicate session %s, ignoring", session["id"])
            return {"received": True, "processed": False, "reason": "duplicate"}

        logger.info(
            "Conversion recorded: session=%s click=%s amount=%s %s",
            session["id"], click_id, session.get("amount_total"), session.get("currency"),
        )
        return {"received": True, "processed": True, "conversion_id": str(conversion.id)}

    # Any other event type: acknowledge but don't process
    return {"received": True, "processed": False, "reason": "unhandled_event_type"}