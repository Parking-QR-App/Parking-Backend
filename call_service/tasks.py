from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from call_service.models import CallRecord
from utils.cache import delete_call_cache

@shared_task
def mark_missed_calls():
    timeout_threshold = timezone.now() - timedelta(seconds=60)
    calls = CallRecord.objects.filter(
        state__in=["initiated", "ringing"],
        created_at__lt=timeout_threshold
    )

    for call in calls:
        call.state = "missed"
        call.updated_at = timezone.now()
        call.save()
        delete_call_cache(call.call_id)

    # Optional log
    print(f"[mark_missed_calls] Marked {calls.count()} calls as missed.")
