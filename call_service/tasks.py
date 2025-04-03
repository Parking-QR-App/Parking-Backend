from celery import shared_task
from django.utils.timezone import now
from .models import Call

@shared_task
def auto_end_expired_calls():
    """Automatically ends calls exceeding 3 minutes."""
    three_min_ago = now() - timezone.timedelta(minutes=3)
    expired_calls = Call.objects.filter(call_status="ongoing", start_time__lt=three_min_ago)

    for call in expired_calls:
        call.end_call(status="ended")

    return f"{expired_calls.count()} calls were auto-ended."
