from celery import shared_task
from .services.settings_service import CallBalanceService

@shared_task
def automated_balance_reset():
    """Celery task for automated balance resets"""
    return CallBalanceService.execute_cron_reset()

@shared_task
def cleanup_old_logs():
    """Clean up balance reset logs older than 90 days"""
    from django.utils import timezone
    from .models import BalanceResetLog
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=90)
    deleted_count, _ = BalanceResetLog.objects.filter(
        created_at__lt=cutoff_date
    ).delete()
    
    return f"Cleaned up {deleted_count} old log entries"