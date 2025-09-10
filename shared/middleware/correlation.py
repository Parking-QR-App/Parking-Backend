import uuid
from shared.logging_context import correlation_id_var

class CorrelationIdMiddleware:
    """
    Middleware that ensures every request has a correlation ID
    and makes it available globally for logging and responses.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Get correlation ID from header or generate one
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.correlation_id = correlation_id

        # Store it in context variable (thread/async safe)
        correlation_id_var.set(correlation_id)

        # Continue processing request
        response = self.get_response(request)

        # Always return correlation ID in response headers
        response["X-Correlation-ID"] = correlation_id
        return response
