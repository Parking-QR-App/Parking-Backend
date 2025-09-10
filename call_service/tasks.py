from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from call_service.models import CallRecord
from .services.call_service import CallReconciliationService, CallService
import logging

logger = logging.getLogger(__name__)

@shared_task
def mark_missed_calls():
    timeout_threshold = timezone.now() - timedelta(seconds=60)
    calls = CallRecord.objects.filter(
        state__in=["initiated", "ringing"],
        created_at__lt=timeout_threshold
    )

    updated_count = 0
    for call in calls:
        call.state = "missed"
        call.updated_at = timezone.now()
        call.save()
        # ✅ update cache instead of delete
        CallService(call.inviter)._update_call_cache(call)
        updated_count += 1

    logger.info(f"[mark_missed_calls] Marked {updated_count} calls as missed.")

@shared_task
def reconcile_failed_call_deductions():
    """Periodic task to reconcile failed call deductions"""
    try:
        result = CallReconciliationService.reconcile_failed_deductions()
        logger.info(
            f"Call deduction reconciliation completed: "
            f"Processed: {result['total_processed']}, "
            f"Reconciled: {result['reconciled']}, "
            f"Still failed: {result['still_failed']}"
        )
        return result
    except Exception as e:
        logger.error(f"Call deduction reconciliation failed: {str(e)}")
        raise
