from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_user
from app.api.v1.helpers import ok
from app.core.errors import not_found
from app.db.session import get_admin_db, get_db
from app.models import Tenant, User
from app.schemas.auth import LoginIn, RefreshIn
from app.schemas.pos import PinIn, VerifyPinIn
from app.services.auth_service import login, refresh, set_pin, verify_pin

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login_route(body: LoginIn, request: Request, session: AsyncSession = Depends(get_admin_db)):
    ip = request.client.host if request.client else None
    return ok(await login(session, body.email, body.password, ip, body.shop))


@router.post("/refresh")
async def refresh_route(body: RefreshIn, session: AsyncSession = Depends(get_admin_db)):
    return ok(await refresh(session, body.refresh_token))


@router.get("/me")
async def me(claims: dict = Depends(require_user), session: AsyncSession = Depends(get_db)):
    user = await session.scalar(select(User).where(User.id == claims["sub"]))
    if user is None:
        raise not_found("User not found")
    tenant = await session.scalar(select(Tenant).where(Tenant.id == user.tenant_id))
    return ok({
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "tenant_id": user.tenant_id,
        "tenant_name": tenant.name if tenant else None,
        "tenant_slug": tenant.slug if tenant else None,
        "roles": claims.get("roles", []),
        "permissions": claims.get("perms", []),
    })


@router.post("/logout")
async def logout(claims: dict = Depends(require_user)):
    # Refresh tokens are rotated on refresh; logout is client-side plus token revocation
    # on the next refresh attempt when the session is discarded.
    return ok({"logged_out": True})


@router.post("/pin")
async def set_my_pin(
    body: PinIn, claims: dict = Depends(require_user), session: AsyncSession = Depends(get_db),
):
    await set_pin(session, claims["sub"], body.pin)
    await session.commit()
    return ok({"pin_set": True})


@router.post("/verify-pin")
async def verify_manager_pin(
    body: VerifyPinIn, _=Depends(require_user), session: AsyncSession = Depends(get_db),
):
    return ok(await verify_pin(session, body.pin, body.permission))
