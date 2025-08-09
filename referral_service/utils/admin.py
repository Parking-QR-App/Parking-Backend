from django.core.exceptions import ValidationError
from ..models import ReferralLimit, ReferralLimitHistory

def set_user_limits(user, daily=None, weekly=None, monthly=None, total=None, actor=None, reason=''):
    try:
        limit = user.referral_limits
    except ReferralLimit.DoesNotExist:
        raise ValidationError("Referral limit not present for user")

    prev = {
        'daily': limit.daily_limit,
        'weekly': limit.weekly_limit,
        'monthly': limit.monthly_limit,
        'total': limit.total_limit,
    }

    if daily is not None:
        limit.daily_limit = daily
    if weekly is not None:
        limit.weekly_limit = weekly
    if monthly is not None:
        limit.monthly_limit = monthly
    if total is not None:
        limit.total_limit = total

    limit.save(update_fields=['daily_limit', 'weekly_limit', 'monthly_limit', 'total_limit', 'updated_at'])

    ReferralLimitHistory.objects.create(
        limit=limit,
        changed_by=actor,
        previous_daily=prev['daily'],
        previous_weekly=prev['weekly'],
        previous_monthly=prev['monthly'],
        previous_total=prev['total'],
        new_daily=limit.daily_limit,
        new_weekly=limit.weekly_limit,
        new_monthly=limit.monthly_limit,
        new_total=limit.total_limit,
        action='set',
        reason=reason or ''
    )
    return limit


def adjust_user_limits(user, delta_daily=0, delta_weekly=0, delta_monthly=0, actor=None, reason=''):
    try:
        limit = user.referral_limits
    except ReferralLimit.DoesNotExist:
        raise ValidationError("Referral limit not present for user")

    prev = {
        'daily': limit.daily_limit,
        'weekly': limit.weekly_limit,
        'monthly': limit.monthly_limit,
        'total': limit.total_limit,
    }

    limit.daily_limit += delta_daily
    limit.weekly_limit += delta_weekly
    limit.monthly_limit += delta_monthly
    limit.save(update_fields=['daily_limit', 'weekly_limit', 'monthly_limit', 'updated_at'])

    action = 'increase' if any(d > 0 for d in [delta_daily, delta_weekly, delta_monthly]) else 'decrease'
    ReferralLimitHistory.objects.create(
        limit=limit,
        changed_by=actor,
        previous_daily=prev['daily'],
        previous_weekly=prev['weekly'],
        previous_monthly=prev['monthly'],
        previous_total=prev['total'],
        new_daily=limit.daily_limit,
        new_weekly=limit.weekly_limit,
        new_monthly=limit.monthly_limit,
        new_total=limit.total_limit,
        action=action,
        reason=reason or ''
    )
    return limit
