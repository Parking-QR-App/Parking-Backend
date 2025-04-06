from celery import shared_task
from django.utils.timezone import now
from .models import User, BlacklistedAccessToken

@shared_task
def clear_expired_otps():
    expired_email_otp_users = User.objects.filter(email_otp_expiry__isnull=False, email_otp_expiry__lt=now())
    expired_email_otp_users.update(email_otp=None, email_otp_expiry=None)

    expired_otp_users = User.objects.filter(otp_expiry__isnull=False, otp_expiry__lt=now())
    expired_otp_users.update(otp=None, otp_expiry=None)

@shared_task
def cleanup_blacklisted_tokens():
    """Deletes all blacklisted tokens daily"""
    deleted_count, _ = BlacklistedAccessToken.objects.all().delete()
    return f"Deleted {deleted_count} blacklisted tokens"
