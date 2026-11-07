import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, org_id: str, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "org": org_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("invalid_token") from exc


MIN_IDLE_TIMEOUT_MINUTES = 20


def idle_timeout_minutes() -> int:
    """Minutes of inactivity after which a login ends; 0 = no inactivity limit. A set value is never below
    MIN_IDLE_TIMEOUT_MINUTES (the access token outlives the last request by up to 15 minutes anyway)."""
    configured = int(settings.SESSION_IDLE_TIMEOUT_MINUTES or 0)
    return 0 if configured <= 0 else max(configured, MIN_IDLE_TIMEOUT_MINUTES)


def refresh_token_lifetime() -> timedelta:
    """How long a freshly issued refresh token stays usable. Every renewal issues a new one, so this is a SLIDING
    window: with an inactivity limit set, a login that is not renewed within it cannot be renewed afterwards."""
    cap = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    idle = idle_timeout_minutes()
    return min(cap, timedelta(minutes=idle)) if idle else cap


def generate_refresh_token() -> tuple[str, str, datetime]:
    """Returns (raw_token, token_hash, expires_at). Only the hash is stored."""
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + refresh_token_lifetime()
    return raw, token_hash, expires_at


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_password_reset_token() -> tuple[str, str, datetime]:
    """Same shape as generate_refresh_token - reuses the identical
    generate-raw/store-hash-only/short-expiry pattern, just with a much
    shorter lifetime (minutes, not days) appropriate to a reset link rather
    than a long-lived session."""
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    return raw, token_hash, expires_at
