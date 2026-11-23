from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import conflict
from app.models.documents import DocumentSequence

PREFIXES = {"INVOICE": "INV", "QUOTE": "QT", "CREDIT_NOTE": "CN", "PAYMENT": "RCPT", "POS_SALE": "BILL"}


async def next_number(
    session: AsyncSession,
    tenant_id: str,
    kind: str,
    *,
    series: str = "MAIN",
    when: date | None = None,
) -> str:
    year = str((when or date.today()).year)
    stmt = select(DocumentSequence).where(
        DocumentSequence.tenant_id == tenant_id,
        DocumentSequence.kind == kind,
        DocumentSequence.series == series,
        DocumentSequence.year == year,
    )
    result = await session.execute(stmt.with_for_update())
    row = result.scalar_one_or_none()
    if row is None:
        if session.get_bind().dialect.name == "postgresql":
            # Race-safe creation: two concurrent first-sales must not both INSERT
            # the sequence row. Insert-or-ignore on the unique key, then lock it.
            await session.execute(
                pg_insert(DocumentSequence)
                .values(
                    tenant_id=tenant_id, kind=kind, series=series, year=year, next_number=1
                )
                .on_conflict_do_nothing(
                    index_elements=["tenant_id", "kind", "series", "year"]
                )
            )
            row = (await session.execute(stmt.with_for_update())).scalar_one()
        else:
            row = DocumentSequence(
                tenant_id=tenant_id, kind=kind, series=series, year=year, next_number=1
            )
            session.add(row)
            await session.flush()
    number = row.next_number
    row.next_number = number + 1
    await session.flush()
    return f"{PREFIXES.get(kind, kind)}-{year}-{number:05d}"
