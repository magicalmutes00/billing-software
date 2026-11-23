from fastapi import APIRouter

from app.api.v1 import (
    audit,
    auth,
    catalog,
    credit_notes,
    customers,
    invoices,
    ops,
    payments,
    portal,
    pos,
    public,
    quotes,
    recurring,
    reports,
    tenants,
    webhooks,
)

router = APIRouter(prefix="/api/v1")
for module in (
    auth, tenants, customers, catalog, quotes, invoices, payments, credit_notes,
    pos, recurring, reports, audit, portal, ops, webhooks, public,
):
    router.include_router(module.router)
