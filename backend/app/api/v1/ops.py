from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.api.v1.helpers import ok
from app.db.session import get_db
from app.services.job_service import run_all

router = APIRouter(prefix="/ops", tags=["ops"])


@router.post("/jobs/run")
async def run_jobs(_=Depends(require_permission("settings.write")), session: AsyncSession = Depends(get_db)):
    return ok(await run_all(session))
