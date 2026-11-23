from contextvars import ContextVar

tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)
actor_id_var: ContextVar[str | None] = ContextVar("actor_id", default=None)
claims_var: ContextVar[dict | None] = ContextVar("claims", default=None)


def current_tenant_id() -> str:
    value = tenant_id_var.get()
    if not value:
        raise RuntimeError("No tenant in context")
    return value


def current_actor_id() -> str | None:
    return actor_id_var.get()
