from celery import shared_task
from django.utils.timezone import now
from .models import User, BlacklistedAccessToken

@shared_task
def clear_expired_otps():
    User.objects.filter(email_otp_expiry__lt=now()).update(email_otp=None, email_otp_expiry=None)
    return "Expired OTPs cleared."

@shared_task
def cleanup_blacklisted_tokens():
    """Deletes all blacklisted tokens daily"""
    deleted_count, _ = BlacklistedAccessToken.objects.all().delete()
    return f"Deleted {deleted_count} blacklisted tokens"
