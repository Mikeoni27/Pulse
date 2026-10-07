from pydantic import BaseModel


class ReferrerStat(BaseModel):
    referrer: str | None
    count: int


class UserAgentStat(BaseModel):
    user_agent: str | None
    count: int


class LinkStats(BaseModel):
    short_code: str
    target_url: str
    total_clicks: int
    clicks_last_24h: int
    clicks_last_7d: int
    top_referrers: list[ReferrerStat]
    top_user_agents: list[UserAgentStat]