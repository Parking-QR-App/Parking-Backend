from django.core.cache import cache
from django.conf import settings

CACHE_TTL = getattr(settings, "CACHE_TTL", 60 * 5)  # default 5 mins

def set_call_cache(call_id, data):
    cache.set(f"call:{call_id}", data, timeout=CACHE_TTL)

def get_call_cache(call_id):
    return cache.get(f"call:{call_id}")

def delete_call_cache(call_id):
    cache.delete(f"call:{call_id}")
