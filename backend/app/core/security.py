from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings

settings = get_settings()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def make_token(
    subject: str,
    tenant_id: str,
    *,
    kind: str = "access",
    minutes: int | None = None,
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    customer_id: str | None = None,
) -> str:
    now = utcnow()
    ttl = minutes if minutes is not None else (
        settings.access_token_minutes if kind == "access" else settings.refresh_token_days * 24 * 60
    )
    payload = {
        "sub": subject,
        "tid": tenant_id,
        "kind": kind,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if roles is not None:
        payload["roles"] = roles
    if permissions is not None:
        payload["perms"] = permissions
    if customer_id is not None:
        payload["cid"] = customer_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, kind: str | None = None) -> dict:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid or expired token") from exc
    if kind and payload.get("kind") != kind:
        raise ValueError("Wrong token type")
    if not payload.get("tid"):
        raise ValueError("Token missing tenant")
    return payload


def new_public_id() -> str:
    return secrets.token_urlsafe(24)
