from django.utils import timezone
from django.db import transaction
from ..models import ReferralCode, Q
from django.core.exceptions import ValidationError
from datetime import timedelta

def validate_referral_code_string(code_str: str) -> bool:
    """
    Basic sanity check for referral code string format.
    """
    if not isinstance(code_str, str) or not code_str.strip():
        return False
    # Additional format constraints can be added here (length, allowed chars, etc.)
    return True


def create_user_referral_code_if_eligible(user) -> ReferralCode | None:
    """
    Create and return a user-type referral code if the user meets criteria:
    first_name, last_name, email present and email_verified == True.
    Idempotent: returns existing active code if present.
    """
    if not getattr(user, 'first_name', None) or not getattr(user, 'last_name', None):
        return None
    if not getattr(user, 'email', None) or not getattr(user, 'email_verified', False):
        return None

    existing = ReferralCode.objects.filter(owner=user, code_type='user', status='active').first()
    if existing:
        return existing

    # Create new code; wrap in transaction in case of race
    with transaction.atomic():
        code_obj = ReferralCode.objects.create(
            owner=user,
            code_type='user',
            status='active',
        )
    return code_obj


def get_active_campaign_codes_for_user(user):
    """
    Return active campaign referral codes that could be applicable for the user.
    (e.g., based on targeting rules - placeholder for future expansion)
    """
    now = timezone.now()
    # Currently simplistic: all active campaign codes not expired
    return ReferralCode.objects.filter(
        code_type='campaign',
        status='active',
        valid_from__lte=now
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=now))


def preflight_validate_referral_application(referrer_code: str, referred_user):
    """
    Validates referral code usage before registering.
    Handles:
    - Invalid format
    - Code not found
    - Status checks
    - Self-referral (if referred_user exists)
    - Already referred (if referred_user exists)
    - Daily, weekly, monthly, total referral limits
    """
    from ..models import ReferralCode, ReferralLimit, ReferralRelationship
    from ..services import CodeValidationError
    from ..utils import validate_referral_code_string  # Assume this exists

    now = timezone.now()

    # I. Validate format
    if not validate_referral_code_string(referrer_code):
        raise ValidationError("Referral code format is invalid")

    # II. Get ReferralCode object
    try:
        code_obj = ReferralCode.objects.select_related("owner").get(code=referrer_code)
    except ReferralCode.DoesNotExist:
        raise ValidationError("Referral code not found")

    referrer = code_obj.owner

    # III. Status Checks
    if code_obj.status != 'active':
        raise CodeValidationError("Referral code is inactive", reason="inactive")

    if code_obj.is_expired:
        raise CodeValidationError("Referral code has expired", reason="expired")

    # III-b. Fetch ReferralLimit object for the referrer
    try:
        referral_limit = ReferralLimit.objects.get(user=referrer)
    except ReferralLimit.DoesNotExist:
        raise ValidationError("Referral limit data not found for this referrer")

    if referral_limit.is_suspended:
        raise CodeValidationError("Referrer's referral privileges are suspended", reason="suspended")

    if not referral_limit.can_refer():
        raise CodeValidationError("Referrer is not allowed to refer due to limit breach", reason="not-allowed")

    # IV. Self-referral & already referred — only if referred_user is not None
    if referred_user:
        if referrer.id == referred_user.id:
            raise ValidationError("You cannot use your own referral code")

        if ReferralRelationship.objects.filter(referred_user=referred_user).exists():
            raise ValidationError("User has already been referred")

    # V. Limits (using ReferralRelationship to count referrals)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    referral_qs = ReferralRelationship.objects.filter(referrer=referrer, referral_code_used=code_obj)

    daily_count = referral_qs.filter(created_at__gte=today_start).count()
    weekly_count = referral_qs.filter(created_at__gte=week_start).count()
    monthly_count = referral_qs.filter(created_at__gte=month_start).count()
    total_count = referral_qs.count()

    if daily_count >= referral_limit.daily_limit:
        raise CodeValidationError("Daily referral limit exceeded", reason="daily-limit")
    if weekly_count >= referral_limit.weekly_limit:
        raise CodeValidationError("Weekly referral limit exceeded", reason="weekly-limit")
    if monthly_count >= referral_limit.monthly_limit:
        raise CodeValidationError("Monthly referral limit exceeded", reason="monthly-limit")
    if referral_limit.total_limit and total_count >= referral_limit.total_limit:
        raise CodeValidationError("Total referral limit exceeded", reason="total-limit")

    return code_obj