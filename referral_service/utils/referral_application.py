from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from ..models import ReferralRelationship, ReferralLimit
from ..utils.limits import check_and_consume_referral_quota
from .events import log_event, EVENT_TYPE_REGISTRATION_COMPLETED
from django.contrib.auth import get_user_model

User = get_user_model()

def apply_referral_code_for_registration(
    referrer_code: str,
    referred_user,
    ip_address: str = None,
    device_type: str = '',
    user_agent: str = ''
) -> ReferralRelationship:
    """
    Main helper to apply a referral code during user registration.
    Assumes preflight validation has already been performed.
    Creates ReferralRelationship and handles quota consumption.
    """
    if referred_user is None:
        raise ValidationError("Referred user must be provided")

    # Fetch the validated code (this should not fail if preflight was successful)
    from ..services.referral_code_service import ReferralCodeService
    code_obj = ReferralCodeService.get_active_code(referrer_code)
    referrer = code_obj.owner or code_obj.created_by_admin

    with transaction.atomic():
        # Lock the limit for safe quota consumption
        referral_limit = ReferralLimit.objects.select_for_update().get(user=referrer)

        # Consume quota (will raise ValidationError if limit exhausted/suspended)
        check_and_consume_referral_quota(referrer, limit_type='daily')

        # Create or get existing relationship (idempotent)
        relationship, created = ReferralRelationship.objects.get_or_create(
            referrer=referrer,
            referred_user=referred_user,
            referral_code_used=code_obj,
            defaults={
                'status': 'pending',
                'registration_ip': ip_address,
                'registration_device_type': device_type,
            }
        )

        if created:
            # Log the referral application / registration-start event
            log_event(
                user=referred_user,
                event_type=EVENT_TYPE_REGISTRATION_COMPLETED,
                referral_code=code_obj,
                referral_relationship=relationship,
                metadata={'stage': 'applied_code'},
                ip_address=ip_address,
                user_agent=user_agent,
                device_type=device_type
            )

            # Update code usage stats (only on first creation)
            code_obj.usage_count = (code_obj.usage_count or 0) + 1
            code_obj.last_used_at = timezone.now()
            code_obj.save(update_fields=['usage_count', 'last_used_at'])

        return relationship