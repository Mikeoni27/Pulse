import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class LinkCreate(BaseModel):
    target_url: HttpUrl = Field(..., max_length=2048)
    custom_code: str | None = Field(None, min_length=3, max_length=16, pattern=r"^[a-zA-Z0-9_-]+$")

    @field_validator("target_url")
    @classmethod
    def reject_private_hosts(cls, v: HttpUrl) -> HttpUrl:
        host = (v.host or "").lower()
        blocked = (
            host == "localhost"
            or host.endswith(".local")
            or host.startswith("127.")
            or host.startswith("10.")
            or host.startswith("192.168.")
            or host == "0.0.0.0"
        )
        if blocked:
            raise ValueError("Target URL cannot point to a private/internal host")
        return v


class LinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    short_code: str
    target_url: str
    is_active: bool
    click_count: int
    created_at: datetime