from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.errors import ApiError, forbidden
from app.core.security import decode_token
from app.db.session import claims_from_request

PUBLIC_PATHS = {"/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/portal/token", "/health", "/ready"}


def claims_of(request: Request) -> dict:
    claims = claims_from_request(request)
    if not claims:
        raise ApiError(401, "UNAUTHENTICATED", "Authentication required")
    return claims


def require_user(request: Request) -> dict:
    claims = claims_of(request)
    if claims.get("kind") != "access":
        raise forbidden("Admin access required")
    return claims


def _approval_grants(request: Request, claims: dict, code: str) -> bool:
    """A short-lived manager-PIN approval token can grant one permission."""
    header = request.headers.get("x-approval-token", "")
    if not header:
        return False
    try:
        approval = decode_token(header.strip(), kind="approval")
    except ValueError:
        return False
    if approval.get("tid") != claims.get("tid"):
        return False
    return code in approval.get("perms", [])


def require_permission(code: str):
    def dependency(request: Request) -> dict:
        claims = require_user(request)
        perms = claims.get("perms", [])
        if code in perms or "all" in perms:
            return claims
        if _approval_grants(request, claims, code):
            return claims
        raise forbidden(f"Missing permission: {code}")

    return dependency


def require_portal(request: Request) -> dict:
    claims = claims_of(request)
    if claims.get("kind") != "portal" or not claims.get("cid"):
        raise forbidden("Portal access required")
    return claims


def pagination(page: int = 1, limit: int = 20) -> tuple[int, int]:
    return max(1, page), min(100, max(1, limit))


CurrentUser = Annotated[dict, Depends(require_user)]
PortalUser = Annotated[dict, Depends(require_portal)]
