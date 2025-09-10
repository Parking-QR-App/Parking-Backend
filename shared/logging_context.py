import contextvars

# Global context variable for correlation ID
correlation_id_var = contextvars.ContextVar("correlation_id", default="-")
