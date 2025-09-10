# shared/utils/context.py
import contextvars
import uuid
from functools import wraps
from django.utils.deprecation import MiddlewareMixin
from typing import Optional, Dict, Any

# Lightweight async-safe request-level context (works for ASGI/Werkzeug/Celery propagation helpers)
request_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar('request_context', default={})


def get_current_request_id() -> str:
    """
    Return the current request id from contextvars or a fallback value.
    Useful in services / utils that are not passed the request object.
    """
    return request_context.get().get('request_id', 'unknown')


def get_current_context() -> Dict[str, Any]:
    """Return the entire current request context dict (may be empty)."""
    return request_context.get()


def get_client_ip_from_request(request) -> Optional[str]:
    """
    Extract client ip robustly from request headers.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('X_FORWARDED_FOR')
    if x_forwarded_for:
        # first value in the comma separated list
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def set_request_context(ctx: Dict[str, Any]) -> contextvars.Token:
    """
    Set the contextvar manually (useful for propagating context into background tasks).
    Returns the token which should be used to reset later.
    """
    return request_context.set(ctx)


def reset_request_context(token: contextvars.Token) -> None:
    """Reset to previous context using token returned by set_request_context."""
    request_context.reset(token)


class RequestContextMiddleware(MiddlewareMixin):
    """
    Middleware to populate a small request-level context accessible via contextvars and request.request_context.
    Add this early in MIDDLEWARE list so downstream code always sees the context.

    Stored keys:
      - request_id: str
      - user_id: Optional[int|str]
      - role: optional user role (if available)
      - tenant_id: optional tenant id (if available)
      - ip_address: str
    """
    def process_request(self, request):
        user = getattr(request, 'user', None)
        ctx = {
            'request_id': request.headers.get('X-Request-ID', str(uuid.uuid4())),
            'user_id': getattr(user, 'id', None),
            # optional fields: role / tenant for multi-tenant or RBAC systems
            'role': getattr(user, 'role', None) if user and hasattr(user, 'role') else None,
            'tenant_id': getattr(user, 'tenant_id', None) if user and hasattr(user, 'tenant_id') else None,
            'ip_address': get_client_ip_from_request(request)
        }
        # store token for reset
        self._token = request_context.set(ctx)
        # store on request for immediate access by code that has request
        request.request_context = ctx
        # also expose correlation id for compatibility with older middleware
        request.correlation_id = ctx['request_id']

    def process_response(self, request, response):
        try:
            ctx = getattr(request, 'request_context', None)
            if ctx and 'request_id' in ctx:
                # expose back to client
                response['X-Request-ID'] = ctx['request_id']
        finally:
            # reset contextvar only if we set it earlier
            if hasattr(self, '_token'):
                request_context.reset(self._token)
        return response


# Helper decorator for carrying request context into sync functions called from views
def with_request_context(func):
    """
    Decorator: capture current context and set it for the function call.
    Useful when spawning threads/tasks synchronously and want to preserve request_id.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        ctx = get_current_context()
        token = set_request_context(ctx)
        try:
            return func(*args, **kwargs)
        finally:
            reset_request_context(token)
    return wrapper
