from __future__ import annotations

from datetime import timedelta, timezone

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.context import current_tenant_id
from app.core.errors import bad_request, forbidden, not_found
from app.core.security import (
    decode_token,
    hash_password,
    make_token,
    token_hash,
    utcnow,
    verify_password,
)
from app.db.session import current_db_tenant, set_tenant_context
from app.models.tenant import (
    Permission,
    RefreshToken,
    Role,
    Tenant,
    User,
    role_permissions,
)

settings = get_settings()

PERMISSIONS = [
    "customers.read", "customers.write",
    "quotes.read", "quotes.write", "quotes.send",
    "invoices.read", "invoices.write", "invoices.send", "invoices.cancel",
    "payments.read", "payments.write", "payments.refund",
    "credit_notes.read", "credit_notes.write",
    "recurring.read", "recurring.write",
    "reports.read", "settings.read", "settings.write",
    "users.read", "users.write", "audit.read",
    "catalog.read", "catalog.write",
    "pos.sell", "pos.void", "pos.reports",
]

OWNER_PERMS = PERMISSIONS
ACCOUNTANT_PERMS = [p for p in PERMISSIONS if p not in {"users.write", "settings.write", "audit.read"}]
VIEWER_PERMS = [p for p in PERMISSIONS if p.endswith(".read")] + ["pos.reports"]
CASHIER_PERMS = ["pos.sell", "pos.reports", "catalog.read", "customers.read"]

ROLE_PERMISSIONS = {
    "OWNER": OWNER_PERMS,
    "ACCOUNTANT": ACCOUNTANT_PERMS,
    "VIEWER": VIEWER_PERMS,
    "CASHIER": CASHIER_PERMS,
}


async def ensure_permissions(session: AsyncSession) -> None:
    existing = set((await session.scalars(select(Permission.code))).all())
    for code in PERMISSIONS:
        if code not in existing:
            session.add(Permission(code=code, description=code.replace(".", " ")))
    await session.flush()


async def sync_all_tenants(session: AsyncSession) -> None:
    """Add new permissions and system roles to tenants created before they existed."""
    await ensure_permissions(session)
    perms = {p.code: p for p in (await session.scalars(select(Permission))).all()}
    tenants = list((await session.scalars(select(Tenant))).all())
    for tenant in tenants:
        previous_tenant = await current_db_tenant(session)
        await set_tenant_context(session, tenant.id)
        try:
            roles = {
                role.name: role
                for role in (
                    await session.scalars(select(Role).where(Role.tenant_id == tenant.id))
                ).all()
            }
            # Preload existing role-permission assignments for this tenant's roles
            # to avoid lazy-loading role.permissions on asyncpg (greenlet issue).
            perm_id_to_code = {p.id: p.code for p in perms.values()}
            existing_role_perms: dict[str, set[str]] = {role.id: set() for role in roles.values()}
            role_ids = [role.id for role in roles.values()]
            if role_ids:
                rp_rows = await session.execute(
                    select(role_permissions.c.role_id, role_permissions.c.permission_id).where(
                        role_permissions.c.role_id.in_(role_ids)
                    )
                )
                for role_id, perm_id in rp_rows.all():
                    existing_role_perms[role_id].add(perm_id_to_code[perm_id])
            for name, codes in ROLE_PERMISSIONS.items():
                role = roles.get(name)
                if role is None:
                    if name != "CASHIER":
                        continue
                    role = Role(
                        tenant_id=tenant.id, name=name, is_system=True, description="Counter cashier"
                    )
                    session.add(role)
                    await session.flush()
                    roles[name] = role
                    existing_role_perms[role.id] = set()
                existing = existing_role_perms[role.id]
                new_perms = [
                    perms[code] for code in codes if code not in existing and code in perms
                ]
                if new_perms:
                    await session.execute(
                        role_permissions.insert().values(
                            [{"role_id": role.id, "permission_id": p.id} for p in new_perms]
                        )
                    )
                    for p in new_perms:
                        existing_role_perms[role.id].add(p.code)
            await session.flush()
        finally:
            await set_tenant_context(session, previous_tenant)
    await session.commit()


async def create_tenant_with_owner(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    email: str,
    password: str,
    full_name: str = "Owner",
    **tenant_fields,
) -> Tenant:
    await ensure_permissions(session)
    perms = {p.code: p for p in (await session.scalars(select(Permission))).all()}
    tenant = Tenant(name=name, slug=slug, settings=tenant_fields.pop("settings", {}), **tenant_fields)
    session.add(tenant)
    await session.flush()

    # Tenant-scoped rows below must be inserted under the new tenant's RLS context.
    previous_tenant = await current_db_tenant(session)
    await set_tenant_context(session, tenant.id)
    try:
        for role_name, codes in ROLE_PERMISSIONS.items():
            role = Role(tenant_id=tenant.id, name=role_name, is_system=True)
            role.permissions = [perms[c] for c in codes]
            session.add(role)
            await session.flush()
            if role_name == "OWNER":
                owner_role = role

        user = User(
            tenant_id=tenant.id,
            email=email.lower(),
            full_name=full_name,
            password_hash=hash_password(password),
            roles=[owner_role],
        )
        session.add(user)
        await session.flush()
    finally:
        await set_tenant_context(session, previous_tenant)
    return tenant


def _token_pair(user: User, perms: list[str], ip: str | None) -> dict:
    roles = [r.name for r in user.roles]
    access = make_token(user.id, user.tenant_id, kind="access", roles=roles, permissions=perms)
    refresh = make_token(
        user.id, user.tenant_id, kind="refresh", minutes=settings.refresh_token_days * 24 * 60
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.access_token_minutes * 60,
    }


async def login(
    session: AsyncSession, email: str, password: str, ip: str | None = None, shop: str | None = None
) -> dict:
    stmt = (
        select(User)
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(User.email == email.lower(), User.status == "ACTIVE")
    )
    if shop:
        stmt = stmt.where(func.lower(Tenant.slug) == shop.strip().lower())
    users = list((await session.scalars(stmt)).all())
    if not users:
        raise bad_request("Invalid email, password or shop code")
    if len(users) > 1:
        raise bad_request("This email is used by more than one shop. Enter a shop code.")
    user = users[0]
    if not verify_password(password, user.password_hash):
        raise bad_request("Invalid email or password")
    perms = sorted({p.code for role in user.roles for p in role.permissions})
    pair = _token_pair(user, perms, ip)
    session.add(
        RefreshToken(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=token_hash(pair["refresh_token"]),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
            created_by_ip=ip,
        )
    )
    user.last_login_at = utcnow()
    await session.flush()
    return pair


async def refresh(session: AsyncSession, token: str) -> dict:
    try:
        payload = decode_token(token, kind="refresh")
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
    record = await session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(token)))
    expires_at = record.expires_at if record else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if record is None or record.revoked_at or expires_at < utcnow():
        raise forbidden("Refresh token is no longer valid")
    user = await session.scalar(
        select(User).where(User.id == payload["sub"], User.tenant_id == payload["tid"])
    )
    if user is None or user.status != "ACTIVE":
        raise not_found("User not found")

    pair = _token_pair(user, sorted({p.code for r in user.roles for p in r.permissions}), None)
    record.revoked_at = utcnow()
    record.replaced_by = token_hash(pair["refresh_token"])
    session.add(
        RefreshToken(
            tenant_id=user.tenant_id,
            user_id=user.id,
            token_hash=token_hash(pair["refresh_token"]),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
        )
    )
    await session.flush()
    return pair


async def set_pin(session: AsyncSession, user_id: str, pin: str) -> None:
    user = await session.scalar(
        select(User).where(User.id == user_id, User.tenant_id == current_tenant_id())
    )
    if user is None:
        raise not_found("User not found")
    user.pin_hash = hash_password(pin)
    await session.flush()


async def verify_pin(session: AsyncSession, pin: str, permission: str) -> dict:
    """Approve a sensitive action with a manager PIN, without a full owner login."""
    users = list((await session.scalars(
        select(User)
        .where(User.tenant_id == current_tenant_id(), User.status == "ACTIVE")
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )).all())
    for user in users:
        if not user.pin_hash or not verify_password(pin, user.pin_hash):
            continue
        perms = {p.code for role in user.roles for p in role.permissions}
        if permission in perms or "all" in perms:
            token = make_token(
                user.id, user.tenant_id, kind="approval", minutes=5, permissions=[permission]
            )
            return {"approval_token": token, "approver": user.full_name, "expires_in": 300}
    raise forbidden("No manager PIN matches that permission")
