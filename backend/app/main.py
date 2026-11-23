from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.context import actor_id_var, tenant_id_var
from app.core.errors import ApiError, api_error_handler
from app.core.security import decode_token
from app.db.session import get_db

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Migrations and seeding run before uvicorn in local dev, but on hosted
    # platforms (Voroa/Render) they can take longer than the health-check
    # startup window because of database latency. seed.py already calls
    # init_db() and sync_all_tenants(), so keep app startup DB-free: the web
    # process can pass /health immediately while the background migration job
    # finishes. Local tests create their schema directly in conftest.py.
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(ApiError, api_error_handler)
app.include_router(v1_router)


@app.middleware("http")
async def tenant_context(request: Request, call_next):
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header.split(" ", 1)[1].strip()
        try:
            claims = decode_token(token)
            request.state.claims = claims
        except (ValueError, KeyError):
            request.state.claims = None
    response = await call_next(request)
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL", "message": "Internal server error"}})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    from sqlalchemy import text

    async for session in get_db():
        await session.execute(text("SELECT 1"))
    return {"status": "ready"}
