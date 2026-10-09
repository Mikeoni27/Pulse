from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request, Response
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

COOKIE_NAME = "pulse_token"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str | Any, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {"sub": str(subject), "exp": expire}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def set_auth_cookie(response: Response, token: str, max_age: int | None = None) -> None:
    """Set the JWT in an HTTP-only cookie for browser sessions.

    `secure` is True only in production so the cookie works on http://localhost in dev.
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max_age or (settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60),
        httponly=True,
        secure=(settings.APP_ENV == "production"),
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def get_token_from_request(request: Request) -> str | None:
    """Read JWT from Authorization header (API) or cookie (browser)."""
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1]
    return request.cookies.get(COOKIE_NAME)