from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission, require_user
from app.api.v1.helpers import ok
from app.core.context import current_tenant_id
from app.core.errors import bad_request, not_found
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Role, Tenant, User
from app.schemas.tenant import SettingsUpdate, TenantOut, TenantUpdate, UserCreate
from app.services.audit import log_audit

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("/me")
async def my_tenant(_=Depends(require_user), session: AsyncSession = Depends(get_db)):
    tenant = await session.scalar(select(Tenant).where(Tenant.id == current_tenant_id()))
    if tenant is None:
        raise not_found("Tenant not found")
    return ok(TenantOut.model_validate(tenant))


@router.patch("/me")
async def update_tenant(
    body: TenantUpdate, _=Depends(require_permission("settings.write")), session: AsyncSession = Depends(get_db)
):
    tenant = await session.scalar(select(Tenant).where(Tenant.id == current_tenant_id()))
    if tenant is None:
        raise not_found("Tenant not found")
    payload = body.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(tenant, field, value)
    await log_audit(session, action="tenant.update", entity_type="tenant", entity_id=tenant.id, after=payload)
    await session.commit()
    return ok(TenantOut.model_validate(tenant))


@router.patch("/me/settings")
async def update_settings(
    body: SettingsUpdate, _=Depends(require_permission("settings.write")), session: AsyncSession = Depends(get_db)
):
    tenant = await session.scalar(select(Tenant).where(Tenant.id == current_tenant_id()))
    if tenant is None:
        raise not_found("Tenant not found")
    tenant.settings = body.settings
    await log_audit(session, action="tenant.settings", entity_type="tenant", entity_id=tenant.id, after=body.settings)
    await session.commit()
    return ok(TenantOut.model_validate(tenant))


@router.get("/users")
async def list_users(_=Depends(require_permission("users.read")), session: AsyncSession = Depends(get_db)):
    rows = (await session.scalars(select(User).where(User.tenant_id == current_tenant_id()))).all()
    return ok([
        {"id": u.id, "email": u.email, "full_name": u.full_name, "status": u.status,
         "roles": [r.name for r in u.roles]}
        for u in rows
    ])


@router.post("/users", status_code=201)
async def create_user(
    body: UserCreate, _=Depends(require_permission("users.write")), session: AsyncSession = Depends(get_db)
):
    duplicate = await session.scalar(select(User).where(User.tenant_id == current_tenant_id(), User.email == body.email.lower()))
    if duplicate:
        raise bad_request("A user with this email already exists")
    roles = (await session.scalars(select(Role).where(
        Role.tenant_id == current_tenant_id(), Role.name.in_(body.roles or ["VIEWER"])
    ))).all()
    if not roles:
        raise bad_request("No valid roles supplied")
    user = User(tenant_id=current_tenant_id(), email=body.email.lower(), full_name=body.full_name,
                password_hash=hash_password(body.password), roles=list(roles))
    session.add(user)
    await log_audit(session, action="user.create", entity_type="user", entity_id=user.id,
                    after={"email": user.email, "roles": body.roles})
    await session.commit()
    return ok({"id": user.id, "email": user.email, "full_name": user.full_name, "status": user.status,
               "roles": [r.name for r in user.roles]})


@router.get("/roles")
async def list_roles(_=Depends(require_permission("users.read")), session: AsyncSession = Depends(get_db)):
    rows = (await session.scalars(select(Role).where(Role.tenant_id == current_tenant_id()))).all()
    return ok([{"id": r.id, "name": r.name, "description": r.description,
                "permissions": [p.code for p in r.permissions]} for r in rows])
