"""Tier definitions and limits.

Single source of truth for what each subscription tier allows.
"""

TIERS = {
    "free": {
        "name": "Free",
        "max_links": 20,
        "max_clicks_per_month": 5_000,
        "analytics_retention_days": 10,
    },
    "pro": {
        "name": "Pro",
        "max_links": None,  # Unlimited
        "max_clicks_per_month": 1_000_000,
        "analytics_retention_days": 365,
    },
    "business": {
        "name": "Business",
        "max_links": None,  # Unlimited
        "max_clicks_per_month": None,  # Unlimited
        "analytics_retention_days": None,  # Forever
    },
}


def get_tier(tier_name: str) -> dict:
    """Get tier config by name. Falls back to free tier."""
    return TIERS.get(tier_name, TIERS["free"])


def is_unlimited(value: int | None) -> bool:
    return value is None