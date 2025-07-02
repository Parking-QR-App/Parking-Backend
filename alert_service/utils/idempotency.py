from django.core.cache import cache
from django.core.exceptions import ValidationError
import uuid

class IdempotencyKey:
    @staticmethod
    def generate():
        return str(uuid.uuid4())

    @staticmethod
    def check_and_set(key: str, timeout=86400):
        if not key:
            return True
            
        cache_key = f"idempotency:{key}"
        if cache.get(cache_key):
            raise ValidationError("Duplicate request detected")
        cache.set(cache_key, True, timeout=timeout)
        return True