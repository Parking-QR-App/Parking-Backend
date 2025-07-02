import json
import redis
from django.conf import settings

# Setup Redis client
redis_client = redis.StrictRedis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=0,
    decode_responses=True
)

REDIS_CALL_PREFIX = "CALL_RECORD:"
REDIS_TTL_SECONDS = 300  # 5 minutes

def get_call_cache(call_id):
    key = f"{REDIS_CALL_PREFIX}{call_id}"
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None

def set_call_cache(call_id, payload):
    key = f"{REDIS_CALL_PREFIX}{call_id}"
    redis_client.setex(key, REDIS_TTL_SECONDS, json.dumps(payload))
