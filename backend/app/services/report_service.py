from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import current_tenant_id
from app.models import Invoice, InvoiceItem, Payment, Role, Tenant, User


async def shops_summary(session: AsyncSession, user_id: str) -> list[dict]:
    """Consolidated counter KPIs across every shop the user's email belongs to.

    Runs on the privileged owner connection (cross-tenant by design).
    """
    actor = await session.scalar(select(User).where(User.id == user_id))
    if actor is None:
        return []
    users = list((await session.scalars(
        select(User)
        .where(func.lower(User.email) == actor.email.lower(), User.status == "ACTIVE")
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )).all())
    today = date.today()
    shops: list[dict] = []
    for user in users:
        perms = {p.code for role in user.roles for p in role.permissions}
        if not (perms & {"reports.read", "pos.reports", "all"}):
            continue
        tenant = await session.scalar(select(Tenant).where(Tenant.id == user.tenant_id))
        rows = list((await session.scalars(
            select(Invoice).where(
                Invoice.tenant_id == user.tenant_id,
                Invoice.channel == "POS",
                Invoice.issue_date == today,
                Invoice.status != "CANCELLED",
            )
        )).all())
        gross = sum(max(0, row.total_paise - int((row.pos_meta or {}).get("refunded_paise", 0))) for row in rows)
        shops.append({
            "tenant_id": user.tenant_id,
            "tenant_name": tenant.name if tenant else None,
            "slug": tenant.slug if tenant else None,
            "today_sales": len(rows),
            "today_gross_paise": gross,
            "role": user.roles[0].name if user.roles else None,
        })
    return shops


async def dashboard(session: AsyncSession) -> dict:
    invoices = (await session.scalars(
        select(Invoice).where(Invoice.tenant_id == current_tenant_id(), Invoice.status != "CANCELLED")
    )).all()
    billed = sum(i.total_paise for i in invoices)
    outstanding = sum(i.balance_paise for i in invoices)
    overdue = sum(i.balance_paise for i in invoices if i.status == "OVERDUE" or i.due_date < date.today())
    payments = (await session.scalars(
        select(Payment).where(Payment.tenant_id == current_tenant_id(), Payment.status == "CAPTURED")
    )).all()
    month_start = date.today().replace(day=1)
    this_month = sum(
        p.amount_paise for p in payments
        if p.paid_at and p.paid_at.date() >= month_start
    )
    return {
        "billed_paise": billed,
        "collected_paise": sum(p.amount_paise for p in payments),
        "outstanding_paise": outstanding,
        "overdue_paise": overdue,
        "this_month_paise": this_month,
        "invoice_counts": {
            status: sum(1 for i in invoices if i.status == status)
            for status in ["DRAFT", "SENT", "PARTIALLY_PAID", "PAID", "OVERDUE"]
        },
    }


async def ar_aging(session: AsyncSession) -> list[dict]:
    invoices = (await session.scalars(
        select(Invoice).where(
            Invoice.tenant_id == current_tenant_id(),
            Invoice.balance_paise > 0,
            Invoice.status != "CANCELLED",
        )
    )).all()
    buckets = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    for invoice in invoices:
        days = max(0, (date.today() - invoice.due_date).days)
        key = "0-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
        buckets[key] += invoice.balance_paise
    return [{"bucket": k, "amount_paise": v} for k, v in buckets.items()]


async def collections(session: AsyncSession, months: int = 12) -> list[dict]:
    payments = (await session.scalars(
        select(Payment).where(Payment.tenant_id == current_tenant_id(), Payment.status == "CAPTURED")
    )).all()
    totals: dict[str, int] = defaultdict(int)
    for payment in payments:
        if payment.paid_at:
            totals[payment.paid_at.strftime("%Y-%m")] += payment.amount_paise
    start = date.today().replace(day=1)
    result = []
    for index in range(months - 1, -1, -1):
        year = start.year - (index // 12)
        month = start.month - (index % 12)
        if month <= 0:
            month += 12
            year -= 1
        key = f"{year:04d}-{month:02d}"
        result.append({"month": key, "amount_paise": totals.get(key, 0)})
    return result


async def gst_summary(session: AsyncSession) -> list[dict]:
    invoice_ids = select(Invoice.id).where(Invoice.tenant_id == current_tenant_id(), Invoice.status != "CANCELLED")
    items = (await session.scalars(
        select(InvoiceItem).where(InvoiceItem.tenant_id == current_tenant_id(), InvoiceItem.invoice_id.in_(invoice_ids))
    )).all()
    totals: dict[tuple[float, str], dict] = defaultdict(
        lambda: {"taxable_paise": 0, "cgst_paise": 0, "sgst_paise": 0, "igst_paise": 0, "tax_paise": 0}
    )
    for item in items:
        kind = "IGST" if item.igst_paise else "CGST_SGST"
        row = totals[(item.tax_rate_pct, kind)]
        row["taxable_paise"] += item.taxable_paise
        row["cgst_paise"] += item.cgst_paise
        row["sgst_paise"] += item.sgst_paise
        row["igst_paise"] += item.igst_paise
        row["tax_paise"] += item.tax_paise
    return [
        {"rate": rate, "type": kind, **values}
        for (rate, kind), values in sorted(totals.items())
    ]


async def sales(session: AsyncSession, months: int = 12) -> list[dict]:
    invoices = (await session.scalars(
        select(Invoice).where(Invoice.tenant_id == current_tenant_id(), Invoice.status != "CANCELLED")
    )).all()
    totals: dict[str, int] = defaultdict(int)
    for invoice in invoices:
        key = invoice.issue_date.strftime("%Y-%m") if hasattr(invoice.issue_date, "strftime") else str(invoice.issue_date)[:7]
        totals[key] += invoice.total_paise
    return [{"month": k, "amount_paise": v} for k, v in sorted(totals.items())[-months:]]
