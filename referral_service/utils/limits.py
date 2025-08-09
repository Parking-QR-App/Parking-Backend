from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError

from ..models import ReferralLimit, ReferralLimitHistory


def check_and_consume_referral_quota(user, limit_type='daily') -> bool:
    """
    Check if user can refer and consume one unit of quota atomically.
    Returns True if consumed, raises ValidationError otherwise.
    """
    try:
        limit = user.referral_limits
    except ReferralLimit.DoesNotExist:
        raise ValidationError("Referral limit not configured for user")

    if limit.is_suspended:
        raise ValidationError("Referrals suspended for this user")

    if limit.is_unlimited:
        return True  # nothing to consume

    with transaction.atomic():
        can = limit.can_refer(limit_type)
        if not can:
            raise ValidationError(f"{limit_type.capitalize()} limit reached")

        prev = {
            'daily': limit.daily_used,
            'weekly': limit.weekly_used,
            'monthly': limit.monthly_used,
            'total': limit.total_used,
        }

        # consume appropriate counter
        if limit_type == 'daily':
            limit.daily_used += 1
        elif limit_type == 'weekly':
            limit.weekly_used += 1
        elif limit_type == 'monthly':
            limit.monthly_used += 1
        elif limit_type == 'total':
            limit.total_used += 1
        else:
            raise ValidationError("Unknown limit type")

        limit.save(update_fields=[f"{limit_type}_used", 'updated_at'])

        # Record history for consumption as 'increase' of used? Could be a separate audit; skipping for usage counters.
    return True


def reset_limits_if_needed(limit: ReferralLimit):
    """
    Reset daily/weekly/monthly counters if their window has rolled over.
    Intended to be invoked by a scheduler (e.g., cron/Celery beat).
    """
    now = timezone.now()
    updates = {}
    # Daily reset (>=1 day)
    if (now - limit.daily_reset_at).days >= 1:
        updates['daily_used'] = 0
        updates['daily_reset_at'] = now
    # Weekly reset (>=7 days)
    if (now - limit.weekly_reset_at).days >= 7:
        updates['weekly_used'] = 0
        updates['weekly_reset_at'] = now
    # Monthly reset (calendar month change)
    if now.month != limit.monthly_reset_at.month or now.year != limit.monthly_reset_at.year:
        updates['monthly_used'] = 0
        updates['monthly_reset_at'] = now

    if updates:
        for field, value in updates.items():
            setattr(limit, field, value)
        limit.save(update_fields=list(updates.keys()) + ['updated_at'])


def boost_user_limit(user, delta_daily=0, delta_weekly=0, delta_monthly=0, reason=''):
    """
    Temporarily or permanently increase limits. Records history with before/after values.
    """
    try:
        limit = user.referral_limits
    except ReferralLimit.DoesNotExist:
        raise ValidationError("Referral limit not configured for user")

    prev = {
        'daily': limit.daily_limit,
        'weekly': limit.weekly_limit,
        'monthly': limit.monthly_limit,
        'total': limit.total_limit,
    }

    if delta_daily:
        limit.daily_limit += delta_daily
    if delta_weekly:
        limit.weekly_limit += delta_weekly
    if delta_monthly:
        limit.monthly_limit += delta_monthly

    limit.save(update_fields=['daily_limit', 'weekly_limit', 'monthly_limit', 'updated_at'])

    ReferralLimitHistory.objects.create(
        limit=limit,
        changed_by=None,
        previous_daily=prev['daily'],
        previous_weekly=prev['weekly'],
        previous_monthly=prev['monthly'],
        previous_total=prev['total'],
        new_daily=limit.daily_limit,
        new_weekly=limit.weekly_limit,
        new_monthly=limit.monthly_limit,
        new_total=limit.total_limit,
        action='boost',
        reason=reason or ''
    )
    return limit


def suspend_user_referrals(user, reason=''):
    """
    Suspend a user's ability to refer.
    """
    try:
        limit = user.referral_limits
    except ReferralLimit.DoesNotExist:
        raise ValidationError("Referral limit not configured for user")

    prev = {
        'daily': limit.daily_limit,
        'weekly': limit.weekly_limit,
        'monthly': limit.monthly_limit,
        'total': limit.total_limit,
    }

    limit.is_suspended = True
    limit.suspension_reason = reason
    limit.save(update_fields=['is_suspended', 'suspension_reason', 'updated_at'])

    ReferralLimitHistory.objects.create(
        limit=limit,
        changed_by=None,
        previous_daily=prev['daily'],
        previous_weekly=prev['weekly'],
        previous_monthly=prev['monthly'],
        previous_total=prev['total'],
        new_daily=limit.daily_limit,
        new_weekly=limit.weekly_limit,
        new_monthly=limit.monthly_limit,
        new_total=limit.total_limit,
        action='disable',
        reason=reason or ''
    )
    return limit


def resume_user_referrals(user):
    """
    Resume a previously suspended user.
    """
    try:
        limit = user.referral_limits
    except ReferralLimit.DoesNotExist:
        raise ValidationError("Referral limit not configured for user")

    prev = {
        'daily': limit.daily_limit,
        'weekly': limit.weekly_limit,
        'monthly': limit.monthly_limit,
        'total': limit.total_limit,
    }

    limit.is_suspended = False
    limit.suspension_reason = ''
    limit.save(update_fields=['is_suspended', 'suspension_reason', 'updated_at'])

    ReferralLimitHistory.objects.create(
        limit=limit,
        changed_by=None,
        previous_daily=prev['daily'],
        previous_weekly=prev['weekly'],
        previous_monthly=prev['monthly'],
        previous_total=prev['total'],
        new_daily=limit.daily_limit,
        new_weekly=limit.weekly_limit,
        new_monthly=limit.monthly_limit,
        new_total=limit.total_limit,
        action='resume',
        reason='Resumed referrals'
    )
    return limit
