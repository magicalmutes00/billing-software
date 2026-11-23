from typing import Any


def ok(data: Any, meta: dict | None = None) -> dict:
    result: dict[str, Any] = {"data": data}
    if meta is not None:
        result["meta"] = meta
    return result


def page_meta(total: int, page: int, limit: int) -> dict:
    return {"total": total, "page": page, "limit": limit, "pages": max(1, (total + limit - 1) // limit)}
