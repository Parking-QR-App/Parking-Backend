from celery import shared_task
from django.utils.timezone import now
from .models import User, BlacklistedAccessToken


@shared_task
def clear_expired_otps():
    """
    Clears expired email OTPs from the User model.
    This helps avoid misuse and ensures cleaner data.
    """
    expired_users = User.objects.filter(email_otp_expiry__lt=now())
    count = expired_users.update(email_otp=None, email_otp_expiry=None)
    return f"[OTP Cleanup] Cleared email OTPs for {count} users."


@shared_task
def cleanup_blacklisted_tokens():
    """
    Deletes expired access tokens from the blacklist.
    Helps avoid unbounded DB growth while keeping security intact.
    """
    expired_tokens = BlacklistedAccessToken.objects.filter(expires_at__lt=now())
    count, _ = expired_tokens.delete()
    return f"[Token Cleanup] Deleted {count} expired blacklisted access tokens."
