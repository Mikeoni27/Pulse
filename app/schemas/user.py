import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    created_at: datetime
    subscription_tier: str
    subscription_status: str | None
    subscription_current_period_end: datetime | None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"