from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from jinja2 import Environment
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import current_tenant_id
from app.core.errors import ApiError, bad_request, conflict, not_found
from app.core.security import make_token, utcnow
from app.models import (
    Customer,
    Invoice,
    Modifier,
    ModifierGroup,
    Payment,
    PaymentAllocation,
    PosCashMovement,
    PosShift,
    Product,
    ProductCategory,
    ProductModifierGroup,
    Tenant,
    User,
)
from app.schemas.documents import InvoiceCreate, ItemIn
from app.schemas.payments import AllocationIn, PaymentCreate
from app.schemas.pos import PosPaymentIn, PosRefundIn, PosSaleIn
from app.services import invoice_service, payment_service
from app.services.audit import log_audit
from app.services.numbering import next_number
from app.services.tax import to_paise

ALLOWED_METHODS = {"CASH", "UPI", "CARD"}


async def _tenant(session: AsyncSession) -> Tenant:
    tenant = await session.scalar(select(Tenant).where(Tenant.id == current_tenant_id()))
    if tenant is None:
        raise not_found("Tenant not found")
    return tenant


async def get_or_create_walkin(session: AsyncSession) -> Customer:
    tenant = await _tenant(session)
    customer = await session.scalar(
        select(Customer).where(
            Customer.tenant_id == tenant.id,
            Customer.is_walkin.is_(True),
            Customer.deleted_at.is_(None),
        )
    )
    if customer is not None:
        return customer
    existing = await session.scalar(
        select(Customer).where(
            Customer.tenant_id == tenant.id,
            func.lower(Customer.display_name) == "walk-in customer",
            Customer.deleted_at.is_(None),
        )
    )
    if existing is not None:
        existing.is_walkin = True
        await session.flush()
        return existing
    customer = Customer(
        tenant_id=tenant.id,
        legal_name="Walk-in Customer",
        display_name="Walk-in Customer",
        tax_type="UNREGISTERED",
        state_code=tenant.state_code,
        payment_terms_days=0,
        is_walkin=True,
        addresses=[],
    )
    session.add(customer)
    await session.flush()
    return customer


async def _attached_groups(session: AsyncSession, product_id: str) -> dict[str, ModifierGroup]:
    group_ids = list((await session.scalars(
        select(ProductModifierGroup.group_id).where(
            ProductModifierGroup.tenant_id == current_tenant_id(),
            ProductModifierGroup.product_id == product_id,
        )
    )).all())
    if not group_ids:
        return {}
    groups = (await session.scalars(
        select(ModifierGroup)
        .where(
            ModifierGroup.tenant_id == current_tenant_id(),
            ModifierGroup.id.in_(group_ids),
            ModifierGroup.is_active.is_(True),
        )
        .options(selectinload(ModifierGroup.modifiers))
    )).all()
    return {group.id: group for group in groups}


async def _resolve_line(session: AsyncSession, line) -> dict:
    product = await session.scalar(
        select(Product)
        .where(
            Product.id == line.product_id,
            Product.tenant_id == current_tenant_id(),
            Product.is_active.is_(True),
        )
        .options(selectinload(Product.variants))
    )
    if product is None:
        raise bad_request("One of the products is no longer available")
    category = await session.scalar(
        select(ProductCategory).where(
            ProductCategory.id == product.category_id,
            ProductCategory.tenant_id == current_tenant_id(),
        )
    )
    if category is None or not category.is_active:
        raise bad_request(f"{product.name} is not available right now")

    active_variants = [v for v in product.variants if v.is_active]
    variant = None
    if line.variant_id:
        variant = next((v for v in active_variants if v.id == line.variant_id), None)
        if variant is None:
            raise bad_request(f"Selected size for {product.name} is unavailable")
    else:
        variant = next((v for v in active_variants if v.is_default), None)
        if variant is None and active_variants:
            variant = active_variants[0]

    groups = await _attached_groups(session, product.id)
    selected_ids = set(line.modifier_ids)
    valid_ids = {m.id for group in groups.values() for m in group.modifiers if m.is_active}
    unknown = selected_ids - valid_ids
    if unknown:
        raise bad_request(f"One of the add-ons for {product.name} is unavailable")

    selected: list[Modifier] = []
    for group in groups.values():
        chosen = [m for m in group.modifiers if m.id in selected_ids and m.is_active]
        minimum = max(group.min_select, 1 if group.is_required else 0)
        maximum = group.max_select if group.max_select > 0 else 999
        if len(chosen) < minimum:
            raise bad_request(f"Choose at least {minimum} option(s) for {group.name}")
        if len(chosen) > maximum:
            raise bad_request(f"Choose at most {maximum} option(s) for {group.name}")
        selected.extend(chosen)

    base_price = variant.price_paise if variant is not None else product.base_price_paise
    unit_price = base_price + sum(m.price_paise for m in selected)
    description = product.name
    if variant is not None:
        description += f" ({variant.name})"
    if selected:
        description += " + " + ", ".join(m.name for m in selected)

    item = ItemIn(
        description=description,
        hsn_sac=product.hsn_sac,
        qty=line.qty,
        unit_price_paise=unit_price,
        discount_paise=0,
        tax_rate_pct=product.tax_rate_pct,
    )
    return {
        "item": item,
        "product_id": product.id,
        "variant_id": variant.id if variant is not None else None,
        "modifiers": [
            {"id": m.id, "name": m.name, "price_paise": m.price_paise}
            for m in selected
        ],
        "gross_paise": to_paise(Decimal(str(line.qty)) * Decimal(unit_price)),
    }


def _distribute_discount(grosses: list[int], discount_paise: int) -> list[int]:
    total = sum(grosses)
    if discount_paise <= 0:
        return [0 for _ in grosses]
    if discount_paise > total:
        raise bad_request("Discount cannot exceed the bill subtotal")
    shares: list[int] = []
    remaining = discount_paise
    for index, gross in enumerate(grosses):
        if index == len(grosses) - 1:
            share = remaining
        else:
            share = int(Decimal(discount_paise) * Decimal(gross) / Decimal(total))
            share = min(share, remaining)
            remaining -= share
        shares.append(max(0, share))
    return shares


async def _cashier_name(session: AsyncSession) -> str | None:
    actor_id = session.info.get("actor_id")
    if not actor_id:
        return None
    user = await session.scalar(select(User).where(User.id == actor_id))
    return user.full_name if user is not None else None


def _normalize_payments(data: PosSaleIn, total_paise: int) -> list[dict]:
    raw = data.payments if data.payments else ([data.payment] if data.payment else [PosPaymentIn()])
    tenders: list[dict] = []
    for payment in raw:
        method = payment.method.upper()
        if method not in ALLOWED_METHODS:
            raise bad_request("Payment method must be CASH, UPI or CARD")
        amount = payment.amount_paise
        if amount is None:
            amount = total_paise if len(raw) == 1 else None
        if amount is None:
            raise bad_request("Each split payment must specify amount_paise")
        if amount <= 0:
            raise bad_request("Payment amounts must be greater than zero")
        if method == "CASH":
            tendered = payment.tendered_paise if payment.tendered_paise is not None else amount
            if tendered < amount:
                raise bad_request("Cash tendered is less than the amount due")
            change = tendered - amount
        else:
            tendered = amount
            change = 0
        tenders.append({
            "method": method, "amount_paise": amount, "tendered_paise": tendered,
            "change_paise": change, "reference_no": payment.reference_no,
        })
    if sum(t["amount_paise"] for t in tenders) != total_paise:
        raise bad_request("Payments must add up to the bill total")
    return tenders


async def _post_sale_cash(session: AsyncSession, shift_id: str | None, tenders: list[dict], bill_number: str) -> None:
    cash_amount = sum(t["amount_paise"] for t in tenders if t["method"] == "CASH")
    if cash_amount <= 0:
        return
    if shift_id:
        shift = await session.scalar(
            select(PosShift).where(
                PosShift.id == shift_id, PosShift.tenant_id == current_tenant_id(),
                PosShift.status == "OPEN",
            )
        )
    else:
        shift = await session.scalar(
            select(PosShift).where(
                PosShift.tenant_id == current_tenant_id(), PosShift.status == "OPEN",
            ).order_by(PosShift.opened_at.desc())
        )
    if shift is None:
        return
    session.add(PosCashMovement(
        tenant_id=current_tenant_id(), shift_id=shift.id, type="SALE",
        amount_paise=cash_amount, note=bill_number, user_id=session.info.get("actor_id"),
    ))
    await session.flush()


async def create_sale(session: AsyncSession, data: PosSaleIn) -> Invoice:
    resolved = [await _resolve_line(session, line) for line in data.items]
    grosses = [line["gross_paise"] for line in resolved]
    if sum(grosses) <= 0:
        raise bad_request("Bill total must be greater than zero")

    # Per-line discounts (fixed paise + percentage), then order-level discount
    # distributed over the net line amounts.
    line_discounts: list[int] = []
    for line, resolved_line in zip(data.items, resolved):
        gross = resolved_line["gross_paise"]
        discount = line.discount_paise
        if line.discount_pct:
            discount += to_paise(Decimal(str(line.discount_pct)) * Decimal(gross) / Decimal(100))
        line_discounts.append(min(discount, gross))
    net_grosses = [gross - discount for gross, discount in zip(grosses, line_discounts)]
    order_discounts = _distribute_discount(net_grosses, data.discount_paise)
    items = [
        resolved_line["item"].model_copy(update={"discount_paise": line_d + order_d})
        for resolved_line, line_d, order_d in zip(resolved, line_discounts, order_discounts)
    ]

    customer = await get_or_create_walkin(session)
    settings = (await _tenant(session)).settings or {}
    tax_mode = settings.get("pos_tax_mode", "INCLUSIVE")
    if tax_mode not in {"INCLUSIVE", "EXCLUSIVE"}:
        tax_mode = "INCLUSIVE"
    invoice = await invoice_service.create_invoice(
        session,
        InvoiceCreate(
            customer_id=customer.id,
            issue_date=date.today(),
            due_date=date.today(),
            items=items,
            notes=data.notes,
            tax_mode=tax_mode,
        ),
    )
    if settings.get("pos_round_off", True) is False and invoice.round_off_paise:
        adjustment = invoice.round_off_paise
        invoice.total_paise -= adjustment
        invoice.balance_paise -= adjustment
        invoice.round_off_paise = 0
    invoice.channel = "POS"
    invoice.number = await next_number(
        session, invoice.tenant_id, "POS_SALE", when=invoice.issue_date
    )
    for invoice_item, line in zip(invoice.items, resolved):
        invoice_item.product_id = line["product_id"]
        invoice_item.variant_id = line["variant_id"]
        invoice_item.modifiers = line["modifiers"]

    tenders = _normalize_payments(data, invoice.total_paise)
    cashier = await _cashier_name(session)
    total_tendered = sum(t["tendered_paise"] for t in tenders)
    total_change = sum(t["change_paise"] for t in tenders)
    for tender in tenders:
        await payment_service.create_payment(
            session,
            PaymentCreate(
                customer_id=customer.id,
                amount_paise=tender["amount_paise"],
                method=tender["method"],
                reference_no=tender["reference_no"],
                notes=f"Counter sale {invoice.number}",
                allocations=[AllocationIn(invoice_id=invoice.id, amount_paise=tender["amount_paise"])],
            ),
        )
    invoice.pos_meta = {
        "method": tenders[0]["method"] if len(tenders) == 1 else "SPLIT",
        "tendered_paise": total_tendered,
        "change_paise": total_change,
        "reference_no": tenders[0]["reference_no"] if len(tenders) == 1 else None,
        "cashier": cashier,
        "payments": tenders,
    }
    await session.flush()
    await _post_sale_cash(session, data.shift_id, tenders, invoice.number or "")
    await log_audit(
        session,
        action="pos.sale",
        entity_type="invoice",
        entity_id=invoice.id,
        after={"number": invoice.number, "total_paise": invoice.total_paise, "method": invoice.pos_meta["method"]},
    )
    await session.flush()
    return invoice


async def list_sales(
    session: AsyncSession,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    payment: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[Invoice], int]:
    where = [Invoice.tenant_id == current_tenant_id(), Invoice.channel == "POS"]
    if date_from:
        where.append(Invoice.issue_date >= date_from)
    if date_to:
        where.append(Invoice.issue_date <= date_to)
    if search:
        where.append(func.lower(func.coalesce(Invoice.number, "")).like(f"%{search.lower()}%"))
    rows = list((await session.scalars(
        select(Invoice)
        .where(*where)
        .options(selectinload(Invoice.items))
        .order_by(Invoice.created_at.desc())
    )).all())
    if payment:
        rows = [
            row for row in rows
            if (row.pos_meta or {}).get("method") == payment.upper()
        ]
    total = len(rows)
    start = (page - 1) * limit
    return rows[start:start + limit], total


async def get_sale(session: AsyncSession, sale_id: str) -> Invoice:
    row = await session.scalar(
        select(Invoice)
        .where(
            Invoice.id == sale_id,
            Invoice.tenant_id == current_tenant_id(),
            Invoice.channel == "POS",
        )
        .options(selectinload(Invoice.items))
    )
    if row is None:
        raise not_found("Counter sale not found")
    return row


async def void_sale(session: AsyncSession, sale_id: str, reason: str = "Voided at counter") -> Invoice:
    invoice = await get_sale(session, sale_id)
    if invoice.status == "CANCELLED":
        raise conflict("This sale has already been voided")
    allocations = list((await session.scalars(
        select(PaymentAllocation).where(
            PaymentAllocation.tenant_id == current_tenant_id(),
            PaymentAllocation.invoice_id == invoice.id,
        )
    )).all())
    payment_ids = {allocation.payment_id for allocation in allocations}
    for payment_id in payment_ids:
        try:
            await payment_service.refund_payment(session, payment_id)
        except ApiError:
            pass
    invoice.status = "CANCELLED"
    invoice.balance_paise = 0
    invoice.pos_meta = {
        **(invoice.pos_meta or {}),
        "voided": True,
        "void_reason": reason,
        "voided_at": utcnow().isoformat(),
    }
    await log_audit(
        session,
        action="pos.void",
        entity_type="invoice",
        entity_id=invoice.id,
        after={"number": invoice.number, "reason": reason},
    )
    await session.flush()
    return invoice


async def refund_sale(session: AsyncSession, sale_id: str, data: PosRefundIn) -> Invoice:
    invoice = await get_sale(session, sale_id)
    if invoice.status == "CANCELLED":
        raise conflict("Cannot refund a voided sale")
    meta = invoice.pos_meta or {}
    already = int(meta.get("refunded_paise", 0))
    refundable = invoice.total_paise - already
    if refundable <= 0:
        raise conflict("This sale has already been fully refunded")

    if data.lines:
        items_by_id = {item.id: item for item in invoice.items}
        amount = 0
        for line in data.lines:
            item = items_by_id.get(line.item_id)
            if item is None:
                raise bad_request("Refund line does not belong to this sale")
            if line.qty > item.qty:
                raise bad_request("Refund quantity exceeds the sold quantity")
            amount += to_paise(Decimal(str(line.qty)) / Decimal(str(item.qty)) * Decimal(item.total_paise))
    elif data.amount_paise is not None:
        amount = data.amount_paise
    else:
        amount = refundable
    if amount <= 0:
        raise bad_request("Refund amount must be greater than zero")
    if amount > refundable:
        raise bad_request("Refund exceeds the remaining refundable amount")

    method = (data.method or meta.get("method") or "CASH").upper()
    if method == "SPLIT":
        method = "CASH"
    if method not in ALLOWED_METHODS:
        raise bad_request("Refund method must be CASH, UPI or CARD")

    refund = Payment(
        tenant_id=current_tenant_id(), customer_id=invoice.customer_id,
        amount_paise=amount, method=method, status="REFUNDED",
        notes=f"Refund {invoice.number}: {data.reason}", paid_at=utcnow(),
        created_by=session.info.get("actor_id"), allocations=[],
    )
    session.add(refund)
    await session.flush()

    invoice.paid_paise = max(0, invoice.paid_paise - amount)
    invoice.balance_paise = max(0, invoice.total_paise - invoice.paid_paise - invoice.credited_paise)
    invoice.status = payment_service._invoice_status(invoice)
    refunds = list(meta.get("refunds", []))
    refunds.append({
        "amount_paise": amount, "method": method, "reason": data.reason,
        "at": utcnow().isoformat(), "payment_id": refund.id,
    })
    invoice.pos_meta = {**meta, "refunded_paise": already + amount, "refunds": refunds}

    if method == "CASH":
        shift = await session.scalar(
            select(PosShift).where(
                PosShift.tenant_id == current_tenant_id(), PosShift.status == "OPEN",
            ).order_by(PosShift.opened_at.desc())
        )
        if shift is not None:
            session.add(PosCashMovement(
                tenant_id=current_tenant_id(), shift_id=shift.id, type="REFUND",
                amount_paise=amount, note=invoice.number, user_id=session.info.get("actor_id"),
            ))
    await log_audit(
        session, action="pos.refund", entity_type="invoice", entity_id=invoice.id,
        after={"number": invoice.number, "amount_paise": amount, "reason": data.reason},
    )
    await session.flush()
    return invoice


def _refunded(row: Invoice) -> int:
    return int((row.pos_meta or {}).get("refunded_paise", 0))


def _net(row: Invoice) -> int:
    return max(0, row.total_paise - _refunded(row))


async def _pos_rows(session: AsyncSession, date_from: date, date_to: date) -> list[Invoice]:
    return list((await session.scalars(
        select(Invoice)
        .where(
            Invoice.tenant_id == current_tenant_id(),
            Invoice.channel == "POS",
            Invoice.issue_date >= date_from,
            Invoice.issue_date <= date_to,
            Invoice.status != "CANCELLED",
        )
        .options(selectinload(Invoice.items))
        .order_by(Invoice.created_at)
    )).all())


def _aggregate(rows: list[Invoice]) -> dict:
    gross = sum(_net(row) for row in rows)
    discount = sum(row.discount_paise for row in rows)
    tax = sum(row.tax_paise for row in rows)
    refunded = sum(_refunded(row) for row in rows)
    payment_mix: dict[str, dict] = {}
    hourly = {hour: {"hour": hour, "sales": 0, "amount_paise": 0} for hour in range(24)}
    items: dict[str, dict] = defaultdict(lambda: {"description": "", "qty": 0.0, "amount_paise": 0})
    for row in rows:
        meta = row.pos_meta or {}
        method = meta.get("method") or "UNKNOWN"
        bucket = payment_mix.setdefault(method, {"count": 0, "amount_paise": 0})
        bucket["count"] += 1
        bucket["amount_paise"] += _net(row)
        if row.created_at is not None:
            hourly[row.created_at.hour]["sales"] += 1
            hourly[row.created_at.hour]["amount_paise"] += _net(row)
        for item in row.items:
            entry = items[item.description]
            entry["description"] = item.description
            entry["qty"] += item.qty
            entry["amount_paise"] += item.total_paise
    top_items = sorted(items.values(), key=lambda item: item["amount_paise"], reverse=True)[:10]
    return {
        "sales_count": len(rows),
        "gross_paise": gross,
        "discount_paise": discount,
        "tax_paise": tax,
        "refunded_paise": refunded,
        "average_bill_paise": round(gross / len(rows)) if rows else 0,
        "payment_mix": payment_mix,
        "top_items": top_items,
        "hourly": [hourly[hour] for hour in range(24)],
    }


async def daily_report(session: AsyncSession, day: date) -> dict:
    rows = await _pos_rows(session, day, day)
    return {"date": day.isoformat(), **_aggregate(rows)}


async def range_report(session: AsyncSession, date_from: date, date_to: date) -> dict:
    if date_to < date_from:
        raise bad_request("date_to must be on or after date_from")
    rows = await _pos_rows(session, date_from, date_to)
    summary = _aggregate(rows)
    by_day: dict[str, dict] = {}
    for row in rows:
        key = row.issue_date.isoformat()
        bucket = by_day.setdefault(key, {"date": key, "sales": 0, "amount_paise": 0})
        bucket["sales"] += 1
        bucket["amount_paise"] += _net(row)
    days = [by_day[key] for key in sorted(by_day)]
    # Previous equal-length period for comparison.
    span = (date_to - date_from).days + 1
    prev_to = date_from - timedelta(days=1)
    prev_from = prev_to - timedelta(days=span - 1)
    prev_rows = await _pos_rows(session, prev_from, prev_to)
    previous = _aggregate(prev_rows)
    return {
        "from": date_from.isoformat(),
        "to": date_to.isoformat(),
        **summary,
        "days": days,
        "previous": {
            "from": prev_from.isoformat(), "to": prev_to.isoformat(),
            "sales_count": previous["sales_count"], "gross_paise": previous["gross_paise"],
        },
        "gross_delta_paise": summary["gross_paise"] - previous["gross_paise"],
        "sales_delta": summary["sales_count"] - previous["sales_count"],
    }


async def item_report(session: AsyncSession, date_from: date, date_to: date) -> list[dict]:
    rows = await _pos_rows(session, date_from, date_to)
    items: dict[str, dict] = defaultdict(lambda: {"description": "", "qty": 0.0, "amount_paise": 0, "category": ""})
    for row in rows:
        for item in row.items:
            entry = items[item.description]
            entry["description"] = item.description
            entry["qty"] += item.qty
            entry["amount_paise"] += item.total_paise
    return sorted(items.values(), key=lambda entry: entry["amount_paise"], reverse=True)


async def cashier_report(session: AsyncSession, date_from: date, date_to: date) -> list[dict]:
    rows = await _pos_rows(session, date_from, date_to)
    cashiers: dict[str, dict] = defaultdict(lambda: {"cashier": "", "sales": 0, "amount_paise": 0})
    for row in rows:
        name = (row.pos_meta or {}).get("cashier") or "Unknown"
        entry = cashiers[name]
        entry["cashier"] = name
        entry["sales"] += 1
        entry["amount_paise"] += _net(row)
    return sorted(cashiers.values(), key=lambda entry: entry["amount_paise"], reverse=True)


# ---------- UPI QR + receipt sharing ----------

def upi_intent_uri(upi_id: str, payee_name: str, amount_paise: int, note: str) -> str:
    from urllib.parse import urlencode

    amount = f"{Decimal(amount_paise) / Decimal(100):.2f}"
    params = {"pa": upi_id, "pn": payee_name, "am": amount, "cu": "INR", "tn": note}
    return "upi://pay?" + urlencode(params)


async def upi_qr_svg(session: AsyncSession, amount_paise: int, note: str) -> str:
    import io

    import qrcode
    import qrcode.image.svg

    tenant = await _tenant(session)
    settings = tenant.settings or {}
    upi_id = settings.get("pos_upi_id")
    if not upi_id:
        raise bad_request("Set a UPI ID in counter receipt settings first")
    payee = settings.get("pos_upi_name") or tenant.name
    uri = upi_intent_uri(upi_id, payee, amount_paise, note)
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


async def receipt_share_token(session: AsyncSession, sale_id: str) -> dict:
    invoice = await get_sale(session, sale_id)
    minutes = 60 * 24 * 7
    token = make_token(invoice.id, invoice.tenant_id, kind="receipt", minutes=minutes)
    return {"token": token, "expires_in": minutes * 60}


RECEIPT_TEMPLATE = Environment(autoescape=True).from_string(
    """<!doctype html><html><head><meta charset="utf-8"><title>{{ invoice.number }}</title>
<style>
@page{size:80mm auto;margin:4mm}
*{box-sizing:border-box}
body{font-family:"Courier New",monospace;color:#111;font-size:12px;margin:0;padding:0}
.center{text-align:center}.right{text-align:right}
h1{font-size:16px;margin:0 0 2px;letter-spacing:.5px}
.muted{color:#555}.small{font-size:10px}
hr{border:0;border-top:1px dashed #999;margin:8px 0}
table{width:100%;border-collapse:collapse}
td{padding:2px 0;vertical-align:top}
.name{word-break:break-word}
.total{font-size:15px;font-weight:bold}
.void{color:#b91c1c;font-weight:bold;letter-spacing:2px}
</style></head><body>
<div class="center">
<h1>{{ header }}</h1>
{% if tenant.address_line1 %}<div class="small">{{ tenant.address_line1 }}{% if tenant.city %}, {{ tenant.city }}{% endif %} {{ tenant.pincode or '' }}</div>{% endif %}
{% if phone %}<div class="small">Ph: {{ phone }}</div>{% endif %}
{% if show_gstin and tenant.gstin %}<div class="small">GSTIN: {{ tenant.gstin }}</div>{% endif %}
</div>
<hr>
<div><b>Bill:</b> {{ invoice.number or '—' }} <span class="right" style="float:right">{{ created }}</span></div>
{% if cashier %}<div class="small">Cashier: {{ cashier }}</div>{% endif %}
{% if invoice.status == 'CANCELLED' %}<div class="void center">*** VOID ***</div>{% endif %}
<hr>
<table>
{% for item in invoice.items %}
<tr><td class="name">{{ item.description }}</td></tr>
<tr><td class="muted small">{{ item.qty }} x {{ paise_to_inr(item.unit_price_paise) }}</td><td class="right">{{ paise_to_inr(item.total_paise) }}</td></tr>
{% endfor %}
</table>
<hr>
<table>
<tr><td>Subtotal</td><td class="right">{{ paise_to_inr(invoice.subtotal_paise) }}</td></tr>
{% if invoice.discount_paise %}<tr><td>Discount</td><td class="right">-{{ paise_to_inr(invoice.discount_paise) }}</td></tr>{% endif %}
{% if invoice.round_off_paise %}<tr><td>Round off</td><td class="right">{{ paise_to_inr(invoice.round_off_paise) }}</td></tr>{% endif %}
<tr><td class="total">TOTAL</td><td class="right total">{{ paise_to_inr(invoice.total_paise) }}</td></tr>
<tr><td>Paid by</td><td class="right">{{ method }}</td></tr>
{% if tendered %}<tr><td>Tendered</td><td class="right">{{ paise_to_inr(tendered) }}</td></tr>{% endif %}
{% if change %}<tr><td>Change</td><td class="right">{{ paise_to_inr(change) }}</td></tr>{% endif %}
</table>
<hr>
<div class="center small">{{ footer }}</div>
<div class="center small muted">Powered by Billing</div>
</body></html>"""
)


async def receipt_html(session: AsyncSession, sale_id: str) -> str:
    invoice = await get_sale(session, sale_id)
    tenant = await _tenant(session)
    settings = tenant.settings or {}
    meta = invoice.pos_meta or {}
    created = invoice.created_at.strftime("%d-%m-%Y %H:%M") if invoice.created_at else str(invoice.issue_date)
    return RECEIPT_TEMPLATE.render(
        invoice=invoice,
        tenant=tenant,
        header=settings.get("pos_receipt_header") or tenant.name,
        footer=settings.get("pos_receipt_footer") or "Thank you! Visit again.",
        phone=settings.get("pos_phone") or "",
        show_gstin=settings.get("pos_show_gstin", True),
        cashier=meta.get("cashier"),
        method=meta.get("method", "—"),
        tendered=meta.get("tendered_paise"),
        change=meta.get("change_paise"),
        created=created,
        paise_to_inr=invoice_service.paise_to_inr,
    )
