# auth_service/tasks.py
from celery import shared_task
from django.utils.timezone import now
from .models import User, BlacklistedAccessToken

@shared_task
def clear_expired_otps():
    """
    Clears expired OTPs from the User model.
    """
    # Clear expired email OTPs
    email_expired = User.objects.filter(email_otp_expiry__lt=now())
    email_count = email_expired.update(email_otp=None, email_otp_expiry=None)
    
    # Clear expired phone OTPs
    phone_expired = User.objects.filter(otp_expiry__lt=now())
    phone_count = phone_expired.update(otp=None, otp_expiry=None)
    
    return f"[OTP Cleanup] Cleared {email_count} email OTPs and {phone_count} phone OTPs."

@shared_task
def cleanup_blacklisted_tokens():
    """
    Deletes expired access tokens from the blacklist.
    """
    expired_tokens = BlacklistedAccessToken.objects.filter(expires_at__lt=now())
    count, _ = expired_tokens.delete()
    return f"[Token Cleanup] Deleted {count} expired blacklisted access tokens."

@shared_task
def send_async_email(email, otp, user_name=None):
    """
    Async task to send OTP email
    """
    from .utils import send_otp_email
    send_otp_email(email, otp, user_name)