# shared/utils/circuit_breakers.py
import time
import logging
from functools import wraps
from typing import Callable, Any, Tuple

import requests
from django.db import DatabaseError
from prometheus_client import Counter, Gauge

from shared.utils.api_exceptions import CircuitOpenException

logger = logging.getLogger(__name__)

# Metrics
CIRCUIT_OPEN_COUNT = Counter('circuit_open_total', 'Circuit open events', ['circuit_name'])
CIRCUIT_STATE = Gauge('circuit_state', 'Circuit state (0=closed, 1=open)', ['circuit_name'])
CIRCUIT_FAILURES = Counter('circuit_failures_total', 'Circuit failure events', ['circuit_name'])

# Define exceptions that are considered retryable (should contribute to circuit)
RETRYABLE_EXCEPTIONS: Tuple[type, ...] = (
    requests.RequestException,  # includes ConnectionError, Timeout, etc.
    DatabaseError,              # transient DB issues
    TimeoutError,               # generic timeout
)


class SimpleCircuitBreaker:
    """
    Lightweight circuit breaker intended for external service calls.
    It only trips on retryable exceptions, and records Prometheus metrics.
    Use to wrap calls to external networked services (payment, call provider, etc.).
    """

    def __init__(self, name: str, failure_threshold: int = 5, reset_timeout: int = 30):
        self.name = name
        self.failure_threshold = int(failure_threshold)
        self.reset_timeout = int(reset_timeout)
        self._failures = 0
        self._opened_at = None

    def _is_open(self) -> bool:
        if not self._opened_at:
            return False
        # if opened but reset timeout elapsed, treat as half-open candidate
        return (time.time() - self._opened_at) < self.reset_timeout

    def _open(self) -> None:
        self._opened_at = time.time()
        CIRCUIT_OPEN_COUNT.labels(circuit_name=self.name).inc()
        CIRCUIT_STATE.labels(circuit_name=self.name).set(1)
        logger.warning("Circuit '%s' opened (failures=%s)", self.name, self._failures)

    def _close(self) -> None:
        self._failures = 0
        self._opened_at = None
        CIRCUIT_STATE.labels(circuit_name=self.name).set(0)
        logger.info("Circuit '%s' closed", self.name)

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # if circuit is open, fail fast
            if self._is_open():
                logger.debug("Circuit '%s' is currently open, rejecting call", self.name)
                raise CircuitOpenException(detail=f"Circuit '{self.name}' is open")

            try:
                result = fn(*args, **kwargs)
            except RETRYABLE_EXCEPTIONS as exc:
                # increment failures and possibly open circuit
                self._failures += 1
                CIRCUIT_FAILURES.labels(circuit_name=self.name).inc()
                logger.exception("Retryable exception in circuit '%s': %s", self.name, exc)
                if self._failures >= self.failure_threshold:
                    self._open()
                raise
            except Exception as exc:
                # Non-retryable exceptions do not trip circuit (business/validation errors)
                logger.debug("Non-retryable exception in circuit '%s': %s", self.name, exc)
                raise
            else:
                # On success, reset failures (close circuit)
                if self._failures > 0:
                    self._close()
                return result
        return wrapper


class InstrumentedCircuitBreaker(SimpleCircuitBreaker):
    """
    Same behavior as SimpleCircuitBreaker but with additional instrumentation/logging.
    Provided for convenience (you can use SimpleCircuitBreaker directly).
    """
    def __init__(self, name: str, failure_threshold: int = 5, reset_timeout: int = 30):
        super().__init__(name=name, failure_threshold=failure_threshold, reset_timeout=reset_timeout)


# Pre-configured breakers for common external services used by this monolith.
# Use these to wrap network calls to the named systems.
CALL_SERVICE_BREAKER = InstrumentedCircuitBreaker("call_service", failure_threshold=4, reset_timeout=20)
SUBSCRIPTION_SERVICE_BREAKER = InstrumentedCircuitBreaker("subscription_service", failure_threshold=4, reset_timeout=30)
PAYMENT_SERVICE_BREAKER = InstrumentedCircuitBreaker("payment_service", failure_threshold=4, reset_timeout=30)


# Helper decorator to use the breaker inline on methods:
def circuit_breaker_for(breaker: SimpleCircuitBreaker):
    """
    Decorator factory: @circuit_breaker_for(CALL_SERVICE_BREAKER).
    Use this on small functions that call external resources.
    """
    def decorator(func):
        return breaker(func)
    return decorator
