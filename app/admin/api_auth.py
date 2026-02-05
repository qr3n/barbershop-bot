from __future__ import annotations

from datetime import timedelta

from fastapi import Cookie, Depends, HTTPException, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import Settings, get_settings


COOKIE_NAME = "admin_session"
MAX_AGE_SECONDS = int(timedelta(days=7).total_seconds())


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    if not settings.admin_session_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_SESSION_SECRET is not configured",
        )
    return URLSafeTimedSerializer(settings.admin_session_secret, salt="admin-session")


def set_admin_cookie(response: Response, *, settings: Settings) -> None:
    s = _serializer(settings)
    token = s.dumps({"v": 1})

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=MAX_AGE_SECONDS,
        httponly=True,
        secure=bool(settings.admin_cookie_secure),
        samesite="lax",
        domain=settings.admin_cookie_domain,
        path="/",
    )


def clear_admin_cookie(response: Response, *, settings: Settings) -> None:
    response.delete_cookie(key=COOKIE_NAME, domain=settings.admin_cookie_domain, path="/")


def verify_admin_cookie(
    token: str | None,
    *,
    settings: Settings,
) -> None:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    s = _serializer(settings)
    try:
        s.loads(token, max_age=MAX_AGE_SECONDS)
    except SignatureExpired as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired") from e
    except BadSignature as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from e


def require_admin(
    admin_session: str | None = Cookie(default=None, alias=COOKIE_NAME),
    settings: Settings = Depends(get_settings),
) -> None:
    verify_admin_cookie(admin_session, settings=settings)
