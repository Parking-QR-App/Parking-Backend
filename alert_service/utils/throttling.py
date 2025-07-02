from django_ratelimit.decorators import ratelimit
from django_ratelimit.core import is_ratelimited
from functools import wraps
from django.http import JsonResponse

def custom_ratelimit(key='user', rate='10/m'):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if is_ratelimited(request, key=key, rate=rate, increment=True):
                return JsonResponse(
                    {"error": "Too many requests"}, 
                    status=429
                )
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator