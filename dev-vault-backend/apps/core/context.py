from contextvars import ContextVar

correlation_id_context: ContextVar[str | None] = ContextVar("correlation_id", default=None)

source_ip_context = ContextVar("source_ip", default=None)
