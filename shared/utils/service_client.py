# # shared/utils/service_client.py
# import uuid
# import time
# import logging
# import requests
# from dataclasses import dataclass
# from enum import Enum
# from functools import wraps
# from typing import Any, Callable, Dict, Optional

# from django.conf import settings
# from django.core.cache import cache

# from prometheus_client import Counter, Histogram

# from shared.utils.api_exceptions import (
#     ServiceCallException,
#     ServiceTimeoutException,
#     ServiceUnavailableException,
#     RateLimitExceededException,
# )

# logger = logging.getLogger(__name__)

# # Metrics
# SERVICE_CALL_COUNTER = Counter(
#     "service_calls_total",
#     "Total service calls",
#     ["service", "endpoint", "status"]
# )
# SERVICE_CALL_DURATION = Histogram(
#     "service_call_duration_seconds",
#     "Service call duration",
#     ["service", "endpoint"]
# )

# # -------------------------
# # Circuit Breaker primitives
# # -------------------------
# class CircuitState(Enum):
#     CLOSED = "CLOSED"
#     OPEN = "OPEN"
#     HALF_OPEN = "HALF_OPEN"

# @dataclass
# class CircuitBreakerConfig:
#     failure_threshold: int = 5            # failures before we OPEN
#     reset_timeout: int = 60               # seconds to attempt HALF_OPEN
#     half_open_max_calls: int = 3          # successes to fully CLOSE

# CB_CACHE_PREFIX = "CB:STATE:"  # short, cheap to scan; redis behind django-cache will namespace itself

# class CircuitBreaker:
#     """
#     Distributed circuit-breaker using Django cache (backed by Redis in your env).
#     Stores a single state blob per service name:
#       { 'state': 'OPEN'|'CLOSED'|'HALF_OPEN',
#         'failure_count': int,
#         'last_failure_time': float,
#         'half_open_success_count': int }
#     """
#     def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
#         self.name = name
#         self.config = config or CircuitBreakerConfig()
#         self.state = CircuitState.CLOSED
#         self.failure_count = 0
#         self.last_failure_time = 0.0
#         self.half_open_success_count = 0

#     @property
#     def _cache_key(self) -> str:
#         return f"{CB_CACHE_PREFIX}{self.name}"

#     def _load_state(self) -> None:
#         blob = cache.get(self._cache_key)
#         if not blob:
#             # fresh default
#             return
#         try:
#             self.state = CircuitState(blob.get("state", "CLOSED"))
#             self.failure_count = int(blob.get("failure_count", 0))
#             self.last_failure_time = float(blob.get("last_failure_time", 0.0))
#             self.half_open_success_count = int(blob.get("half_open_success_count", 0))
#         except Exception:
#             # if corrupted, reset
#             logger.warning("CircuitBreaker state corrupted for %s; resetting", self.name)
#             self._save_state()

#     def _save_state(self) -> None:
#         blob = {
#             "state": self.state.value,
#             "failure_count": self.failure_count,
#             "last_failure_time": self.last_failure_time,
#             "half_open_success_count": self.half_open_success_count,
#         }
#         # TTL > reset_timeout; 1 hour is sane default
#         cache.set(self._cache_key, blob, timeout=max(3600, self.config.reset_timeout * 2))

#     def _record_failure(self) -> None:
#         self.failure_count += 1
#         self.last_failure_time = time.time()

#         if self.state == CircuitState.CLOSED and self.failure_count >= self.config.failure_threshold:
#             self.state = CircuitState.OPEN
#         elif self.state == CircuitState.HALF_OPEN:
#             # any failure during HALF_OPEN -> OPEN again immediately
#             self.state = CircuitState.OPEN

#         self._save_state()

#     def _record_success(self) -> None:
#         if self.state == CircuitState.HALF_OPEN:
#             self.half_open_success_count += 1
#             if self.half_open_success_count >= self.config.half_open_max_calls:
#                 # restore to CLOSED & reset counters
#                 self.state = CircuitState.CLOSED
#                 self.failure_count = 0
#                 self.half_open_success_count = 0
#         else:
#             # closed path; keep failure_count down
#             self.failure_count = 0
#         self._save_state()

#     def execute(self, operation: Callable[[], Any]) -> Any:
#         self._load_state()

#         if self.state == CircuitState.OPEN:
#             if time.time() > (self.last_failure_time + self.config.reset_timeout):
#                 # Try half-open probes
#                 self.state = CircuitState.HALF_OPEN
#                 self.half_open_success_count = 0
#                 self._save_state()
#             else:
#                 raise ServiceUnavailableException(
#                     detail=f"Circuit breaker open for {self.name}"
#                 )

#         try:
#             result = operation()
#             self._record_success()
#             return result
#         except Exception:
#             self._record_failure()
#             raise

# # -------------------------
# # Retry decorator
# # -------------------------
# class RetryConfig:
#     def __init__(self, max_retries: int = 3, backoff_factor: float = 0.1,
#                  retry_on: tuple = (500, 502, 503, 504, 429)):
#         self.max_retries = max_retries
#         self.backoff_factor = backoff_factor
#         self.retry_on = retry_on

# def retry(config: Optional[RetryConfig] = None):
#     config = config or RetryConfig()

#     def decorator(func):
#         @wraps(func)
#         def wrapper(*args, **kwargs):
#             last_exception = None
#             for attempt in range(config.max_retries + 1):
#                 try:
#                     return func(*args, **kwargs)
#                 except ServiceTimeoutException as e:
#                     last_exception = e
#                     # timeouts are retryable
#                 except ServiceCallException as e:
#                     last_exception = e
#                     # check response code if present
#                     resp = getattr(e, "response", None)
#                     code = getattr(resp, "status_code", None)
#                     if code and code not in config.retry_on:
#                         break
#                 except Exception as e:
#                     # For non-service exceptions, do not retry
#                     last_exception = e
#                     break

#                 if attempt == config.max_retries:
#                     break
#                 time.sleep(config.backoff_factor * (2 ** attempt))
#             raise last_exception
#         return wrapper
#     return decorator

# # -------------------------
# # Service Client
# # -------------------------
# class ServiceClient:
#     def __init__(self, service_name: str, cb_config: Optional[CircuitBreakerConfig] = None):
#         self.service_name = service_name
#         self.base_url = settings.SERVICE_URLS[service_name]
#         # Allow per-service overrides from settings if desired
#         settings_cb = getattr(settings, "SERVICE_CIRCUIT_CONFIGS", {}).get(service_name)
#         self.circuit_breaker = CircuitBreaker(service_name, cb_config or settings_cb or CircuitBreakerConfig())

#         self.session = requests.Session()
#         self.session.headers.update({
#             "User-Agent": f"{settings.PROJECT_NAME}-service-client/1.0",
#             "X-Service-Name": settings.SERVICE_NAME,
#         })

#         adapter = requests.adapters.HTTPAdapter(
#             pool_connections=100,
#             pool_maxsize=100,
#             max_retries=0,  # we do our own retry
#         )
#         self.session.mount("http://", adapter)
#         self.session.mount("https://", adapter)

#     @retry(RetryConfig(max_retries=3, backoff_factor=0.1))
#     def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
#         url = f"{self.base_url}/{endpoint.lstrip('/')}"
#         headers = kwargs.pop("headers", {})
#         headers.update(self._get_tracing_headers())

#         with SERVICE_CALL_DURATION.labels(service=self.service_name, endpoint=endpoint).time():
#             try:
#                 response = self.session.request(
#                     method,
#                     url,
#                     headers=headers,
#                     timeout=getattr(settings, "SERVICE_TIMEOUT", 5),
#                     **kwargs,
#                 )
#             except requests.Timeout as e:
#                 SERVICE_CALL_COUNTER.labels(self.service_name, endpoint, "timeout").inc()
#                 raise ServiceTimeoutException(detail=f"Timeout calling {self.service_name}") from e
#             except requests.RequestException as e:
#                 SERVICE_CALL_COUNTER.labels(self.service_name, endpoint, "network_error").inc()
#                 raise ServiceCallException(detail=f"Network error calling {self.service_name}") from e

#             # Response path
#             status_code = response.status_code
#             if status_code == 429:
#                 SERVICE_CALL_COUNTER.labels(self.service_name, endpoint, "http_429").inc()
#                 # Raise typed exception so callers can back off or surface Retry-After
#                 retry_after = int(response.headers.get("Retry-After", "0") or 0)
#                 ex = RateLimitExceededException(retry_after=retry_after, detail=f"Rate limit from {self.service_name}")
#                 ex.response = response  # optional
#                 raise ex

#             if 200 <= status_code < 300:
#                 SERVICE_CALL_COUNTER.labels(self.service_name, endpoint, "success").inc()
#                 return response

#             # 4xx/5xx -> error
#             SERVICE_CALL_COUNTER.labels(self.service_name, endpoint, f"http_{status_code}").inc()
#             ex = ServiceCallException(detail=f"HTTP {status_code} from {self.service_name}")
#             ex.response = response
#             raise ex

#     def _get_tracing_headers(self) -> Dict[str, str]:
#         # If you have a request-scoped correlation id middleware, inject it here instead of generating.
#         return {
#             "X-Request-ID": str(uuid.uuid4()),
#             "X-Correlation-ID": str(uuid.uuid4()),
#             "X-Service-Chain": f"{settings.SERVICE_NAME}->{self.service_name}",
#         }

#     def request(self, method: str, endpoint: str, **kwargs) -> Any:
#         def op():
#             return self._request(method, endpoint, **kwargs)
#         return self.circuit_breaker.execute(op)

#     def get(self, endpoint: str, **kwargs) -> Any:
#         return self.request("GET", endpoint, **kwargs).json()

#     def post(self, endpoint: str, data: Optional[Dict] = None, **kwargs) -> Any:
#         return self.request("POST", endpoint, json=data, **kwargs).json()

#     def put(self, endpoint: str, data: Optional[Dict] = None, **kwargs) -> Any:
#         return self.request("PUT", endpoint, json=data, **kwargs).json()

#     def delete(self, endpoint: str, **kwargs) -> Any:
#         return self.request("DELETE", endpoint, **kwargs).json()

# # Shared instances
# referral_service = ServiceClient("referral_service")
# call_service = ServiceClient("call_service")
# payment_service = ServiceClient("payment_service")
# user_service = ServiceClient("auth_service")
