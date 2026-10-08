import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    click_id: uuid.UUID
    link_id: uuid.UUID
    stripe_session_id: str
    amount: int
    currency: str
    status: str
    customer_email: str | None
    created_at: datetime


class LinkRevenue(BaseModel):
    """Revenue aggregated for a single link."""

    short_code: str
    target_url: str
    total_conversions: int
    total_revenue_cents: int
    currency: str


class AttributionSummary(BaseModel):
    """Overall revenue attribution for a user."""

    total_conversions: int
    total_revenue_cents: int
    currency: str
    top_links: list[LinkRevenue]