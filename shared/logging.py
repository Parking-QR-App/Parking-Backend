import logging
from shared.logging_context import correlation_id_var

class CorrelationIdFilter(logging.Filter):
    """
    Inject correlation_id into log records from contextvars
    """
    def filter(self, record):
        record.correlation_id = correlation_id_var.get()
        return True
