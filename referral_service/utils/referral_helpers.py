from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import ReferralRelationship, ReferralLimit
from ..services.referral_code_service import ReferralCodeService
from ..utils.limits import check_and_consume_referral_quota
from ..utils.events import log_event, EVENT_TYPE_REGISTRATION_COMPLETED


def apply_referral_code_for_registration(
    referrer_code: str,
    referred_user,
    ip_address: str = None,
    device_type: str = '',
    user_agent: str = ''
) -> ReferralRelationship:
    """
    Main helper to apply a referral code during user registration.
    Enforces no self-referral, limits, and creates ReferralRelationship.
    Raises ValidationError on failure.
    """
    if referred_user is None:
        raise ValidationError("Referred user must be provided")

    if not referrer_code:
        raise ValidationError("Referral code is required")

    # Prevent multiple referrals for same referred_user
    if getattr(referred_user, 'referral_source', None):
        raise ValidationError("User has already been referred once")

    # Validate and fetch active code (ensures existence, is_valid, etc.)
    try:
        code_obj = ReferralCodeService.get_active_code(referrer_code)
    except Exception as e:
        raise ValidationError(str(e))

    # Resolve referrer: owner preferred, else admin-created fallback
    referrer = code_obj.owner or code_obj.created_by_admin
    if not referrer:
        raise ValidationError("Referral code has no associated referrer")

    if referrer == referred_user:
        raise ValidationError("Cannot use your own referral code")

    # Ensure referrer has a ReferralLimit (create if missing)
    try:
        referral_limit = referrer.referral_limits
    except ReferralLimit.DoesNotExist:
        referral_limit = ReferralLimit.objects.create(user=referrer)

    with transaction.atomic():
        # Lock the limit for safe quota consumption
        locked_limit = ReferralLimit.objects.select_for_update().get(user=referrer)

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


def mark_referral_converted(relationship: ReferralRelationship, first_payment_amount=None):
    """
    Updates relationship on first payment; sets timestamps and status if eligible.
    """
    now = timezone.now()
    # Only proceed if not already converted/paid
    if relationship.first_payment_at:
        return relationship  # already marked

    relationship.first_payment_at = now
    if first_payment_amount is not None:
        relationship.first_payment_amount = first_payment_amount

    if relationship.created_at:
        delta = relationship.first_payment_at - relationship.created_at
        relationship.days_to_first_payment = delta.days

    # status progression: if previously verified, move to converted
    relationship.status = 'converted'
    relationship.save(update_fields=[
        'first_payment_at',
        'first_payment_amount',
        'days_to_first_payment',
        'status',
        'updated_at'
    ])
    return relationship
