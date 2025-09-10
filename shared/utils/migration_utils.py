# shared/utils/migration_utils.py
import logging
import time
from typing import Callable, List, Optional, Any, Dict, Generator, Tuple
from django.db import transaction
from django.db.models import QuerySet, Model
from contextlib import contextmanager
from prometheus_client import Counter, Histogram, Gauge
import redis
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.conf import settings
from shared.utils.api_exceptions import MigrationLockException

logger = logging.getLogger(__name__)

# -------------------------------
# Prometheus Metrics
# -------------------------------
MIGRATION_DURATION = Histogram(
    'migration_duration_seconds',
    'Migration duration',
    ['migration_name']
)
MIGRATION_SUCCESS = Counter(
    'migration_success_total',
    'Successful migrations',
    ['migration_name']
)
MIGRATION_FAILURE = Counter(
    'migration_failure_total',
    'Failed migrations',
    ['migration_name']
)
MIGRATION_PROGRESS = Gauge(
    'migration_progress_percent',
    'Migration progress percentage',
    ['migration_name']
)


# -------------------------------
# Migration Lock
# -------------------------------
class MigrationLock:
    """Distributed lock for migration operations using Redis."""

    def __init__(self, lock_name: str, timeout: int = 3600) -> None:
        self.lock_name = f"migration_lock:{lock_name}"
        self.timeout = timeout
        self.redis = redis.Redis.from_url(settings.REDIS_URL)
        self.lock_acquired: bool = False

    def __enter__(self) -> "MigrationLock":
        if not self.redis.set(self.lock_name, 1, nx=True, ex=self.timeout):
            raise MigrationLockException(f"Migration lock {self.lock_name} is already held")
        self.lock_acquired = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.lock_acquired:
            try:
                self.redis.delete(self.lock_name)
            except Exception as e:
                logger.error(f"Failed to release migration lock {self.lock_name}: {e}")

    def refresh(self) -> None:
        """Refresh lock timeout to prevent expiry during long migrations."""
        if self.lock_acquired:
            self.redis.expire(self.lock_name, self.timeout)


# -------------------------------
# Batch Processing
# -------------------------------
class BatchProcessor:
    """Process large datasets in batches with progress tracking."""

    def __init__(self, batch_size: int = 1000, max_workers: int = 4, lock: Optional[MigrationLock] = None) -> None:
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.lock = lock

    def process_queryset(
        self,
        queryset: QuerySet,
        process_fn: Callable[[List[Model]], None],
        migration_name: str,
        total_count: Optional[int] = None
    ) -> int:
        """
        Process a queryset in batches with progress tracking.
        Each batch runs inside a transaction.
        """
        total_count = total_count or queryset.count()
        processed = 0
        start_time = time.time()

        MIGRATION_PROGRESS.labels(migration_name=migration_name).set(0)

        for batch in self._batch_queryset(queryset):
            try:
                with transaction.atomic():
                    process_fn(batch)
                processed += len(batch)

                progress = (processed / total_count) * 100
                MIGRATION_PROGRESS.labels(migration_name=migration_name).set(progress)
                logger.info(f"Migration {migration_name}: {processed}/{total_count} ({progress:.1f}%)")

                if self.lock:
                    self.lock.refresh()

            except Exception as e:
                logger.exception(f"Batch processing failed in {migration_name}: {e}")
                MIGRATION_FAILURE.labels(migration_name=migration_name).inc()
                raise

        duration = time.time() - start_time
        MIGRATION_DURATION.labels(migration_name=migration_name).observe(duration)
        MIGRATION_SUCCESS.labels(migration_name=migration_name).inc()

        return processed

    def _batch_queryset(self, queryset: QuerySet) -> Generator[List[Model], None, None]:
        """Yield queryset results in fixed-size batches by PK scan."""
        last_pk = 0
        while True:
            batch = list(queryset.filter(pk__gt=last_pk).order_by("pk")[:self.batch_size])
            if not batch:
                break
            last_pk = batch[-1].pk
            yield batch

    def parallel_process(
        self,
        items: List[Any],
        process_fn: Callable[[Any], Any],
        migration_name: str
    ) -> List[Any]:
        """Process items in parallel using a thread pool."""
        results: List[Any] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(process_fn, item): item for item in items}

            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    item = futures[future]
                    logger.exception(f"Parallel processing failed for item {item} in {migration_name}: {e}")
                    MIGRATION_FAILURE.labels(migration_name=migration_name).inc()

        MIGRATION_SUCCESS.labels(migration_name=migration_name).inc()
        return results


# -------------------------------
# Data Validation
# -------------------------------
class DataValidator:
    """Validate data integrity during migrations."""

    def __init__(self) -> None:
        self.checks: List[Dict[str, Any]] = []

    def add_check(self, name: str, check_fn: Callable[[], Tuple[bool, str]], description: str = "") -> None:
        self.checks.append({
            "name": name,
            "function": check_fn,
            "description": description
        })

    def run_checks(self) -> List[Dict[str, Any]]:
        """Run all validation checks and return results."""
        results: List[Dict[str, Any]] = []
        for check in self.checks:
            try:
                success, message = check["function"]()
                results.append({
                    "name": check["name"],
                    "success": success,
                    "message": message,
                    "description": check["description"]
                })
            except Exception as e:
                logger.exception(f"Validation check {check['name']} failed: {e}")
                results.append({
                    "name": check["name"],
                    "success": False,
                    "message": f"Check failed with exception: {e}",
                    "description": check["description"]
                })
        return results


# -------------------------------
# Context Manager
# -------------------------------
@contextmanager
def migration_context(migration_name: str, lock_timeout: int = 7200):
    """
    Context manager for migration operations with distributed locking
    and automatic metrics tracking.
    """
    lock = MigrationLock(migration_name, lock_timeout)

    try:
        with lock:
            logger.info(f"Starting migration: {migration_name}")
            start_time = time.time()
            yield
            duration = time.time() - start_time
            logger.info(f"Completed migration {migration_name} in {duration:.2f}s")
            MIGRATION_DURATION.labels(migration_name=migration_name).observe(duration)
            MIGRATION_SUCCESS.labels(migration_name=migration_name).inc()
    except MigrationLockException:
        logger.warning(f"Migration {migration_name} is already running elsewhere")
        raise
    except Exception as e:
        logger.exception(f"Migration {migration_name} failed: {e}")
        MIGRATION_FAILURE.labels(migration_name=migration_name).inc()
        raise


# -------------------------------
# Utility Functions
# -------------------------------
def chunked_queryset(queryset: QuerySet, chunk_size: int = 1000) -> Generator[List[Model], None, None]:
    """Efficiently yield queryset results in chunks (memory friendly)."""
    last_pk = 0
    while True:
        chunk = list(queryset.filter(pk__gt=last_pk).order_by("pk")[:chunk_size])
        if not chunk:
            break
        last_pk = chunk[-1].pk
        yield chunk


def estimate_migration_time(total_items: int, items_per_second: float) -> Dict[str, float]:
    """Estimate migration duration in seconds, minutes, and hours."""
    if items_per_second <= 0:
        raise ValueError("items_per_second must be greater than zero")

    total_seconds = total_items / items_per_second
    return {
        "total_items": total_items,
        "estimated_seconds": total_seconds,
        "estimated_minutes": total_seconds / 60,
        "estimated_hours": total_seconds / 3600,
    }
