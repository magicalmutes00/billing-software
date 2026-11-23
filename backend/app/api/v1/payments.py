from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import pagination, require_permission
from app.api.v1.helpers import ok, page_meta
from app.core.context import current_tenant_id
from app.db.session import get_db
from app.models import Payment
from app.providers.payments import get_provider
from app.schemas.payments import AllocateIn, PaymentCreate, PaymentOut, RefundIn
from app.services import payment_service

router = APIRouter(prefix="/payments", tags=["payments"])


class GatewaySessionIn(BaseModel):
    customer_id: str
    amount_paise: int = Field(gt=0)
    invoice_id: str | None = None
    return_url: str = "/portal/invoices"


@router.get("")
async def list_payments(
    customer_id: str | None = None, status: str | None = None, page: int = 1, limit: int = 20,
    _=Depends(require_permission("payments.read")), session: AsyncSession = Depends(get_db),
):
    page, limit = pagination(page, limit)
    rows, total = await payment_service.list_payments(session, customer_id=customer_id, status=status, page=page, limit=limit)
    return ok([PaymentOut.model_validate(row) for row in rows], page_meta(total, page, limit))


@router.post("", status_code=201)
async def create_payment(
    body: PaymentCreate, _=Depends(require_permission("payments.write")), session: AsyncSession = Depends(get_db)
):
    payment = await payment_service.create_payment(session, body)
    await session.commit()
    return ok(PaymentOut.model_validate(payment))


@router.get("/{payment_id}")
async def get_payment(
    payment_id: str, _=Depends(require_permission("payments.read")), session: AsyncSession = Depends(get_db)
):
    return ok(PaymentOut.model_validate(await payment_service.get_payment(session, payment_id)))


@router.post("/{payment_id}/allocate")
async def allocate(
    payment_id: str, body: AllocateIn,
    _=Depends(require_permission("payments.write")), session: AsyncSession = Depends(get_db),
):
    payment = await payment_service.allocate_payment(session, payment_id, body)
    await session.commit()
    return ok(PaymentOut.model_validate(payment))


@router.post("/{payment_id}/refund")
async def refund(
    payment_id: str, body: RefundIn,
    _=Depends(require_permission("payments.refund")), session: AsyncSession = Depends(get_db),
):
    payment = await payment_service.refund_payment(session, payment_id, body.amount_paise)
    await session.commit()
    return ok(PaymentOut.model_validate(payment))


@router.post("/gateway/session")
async def gateway_session(
    body: GatewaySessionIn, _=Depends(require_permission("payments.write")), session: AsyncSession = Depends(get_db)
):
    provider = get_provider()
    payment = Payment(
        tenant_id=current_tenant_id(),
        customer_id=body.customer_id,
        amount_paise=body.amount_paise,
        method="GATEWAY",
        provider=provider.name,
        status="PENDING",
        allocations=[],
    )
    session.add(payment)
    await session.flush()
    if body.invoice_id:
        from app.schemas.payments import AllocationIn
        from app.services.access import get_invoice

        invoice = await get_invoice(session, body.invoice_id)
        await payment_service.apply_allocations(
            session, payment, [AllocationIn(invoice_id=invoice.id, amount_paise=min(body.amount_paise, invoice.balance_paise))]
        )
    result = await provider.create_payment(
        amount_paise=body.amount_paise, currency="INR", order_ref=payment.id, return_url=body.return_url
    )
    payment.provider_ref = result["provider_ref"]
    await session.commit()
    return ok({"payment_id": payment.id, "provider_ref": result["provider_ref"], "checkout_url": result["checkout_url"]})
