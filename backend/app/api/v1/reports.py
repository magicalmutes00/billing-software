from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission, require_user
from app.api.v1.helpers import ok
from app.db.session import get_admin_db, get_db
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/dashboard")
async def dashboard(_=Depends(require_permission("reports.read")), session: AsyncSession = Depends(get_db)):
    return ok(await report_service.dashboard(session))


@router.get("/shops")
async def shops(claims: dict = Depends(require_user), session: AsyncSession = Depends(get_admin_db)):
    return ok(await report_service.shops_summary(session, claims["sub"]))


@router.get("/ar-aging")
async def ar_aging(_=Depends(require_permission("reports.read")), session: AsyncSession = Depends(get_db)):
    return ok(await report_service.ar_aging(session))


@router.get("/collections")
async def collections(months: int = 12, _=Depends(require_permission("reports.read")),
                      session: AsyncSession = Depends(get_db)):
    return ok(await report_service.collections(session, min(months, 24)))


@router.get("/gst-summary")
async def gst_summary(_=Depends(require_permission("reports.read")), session: AsyncSession = Depends(get_db)):
    return ok(await report_service.gst_summary(session))


@router.get("/sales")
async def sales(months: int = 12, _=Depends(require_permission("reports.read")),
                session: AsyncSession = Depends(get_db)):
    return ok(await report_service.sales(session, min(months, 24)))
