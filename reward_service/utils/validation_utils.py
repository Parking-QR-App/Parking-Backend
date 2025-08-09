from django.utils import timezone
from typing import Dict, Optional, Any
from datetime import timedelta
from decimal import Decimal


def validate_reward_eligibility(user, reward_type: str, reward_config, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Top-level validator: Checks eligibility for a reward config and type.
    """
    if not reward_config.is_active:
        return {
            'eligible': False,
            'error': 'REWARD_CONFIG_INACTIVE',
            'message': 'This reward is currently inactive'
        }

    now = timezone.now()

    if reward_config.valid_from and now < reward_config.valid_from:
        return {
            'eligible': False,
            'error': 'REWARD_NOT_YET_VALID',
            'message': f'Reward will be valid from {reward_config.valid_from}'
        }

    if reward_config.valid_until and now > reward_config.valid_until:
        return {
            'eligible': False,
            'error': 'REWARD_EXPIRED',
            'message': f'Reward expired on {reward_config.valid_until}'
        }

    # Basic eligibility check
    basic_check = _check_user_eligibility_criteria(user, reward_type, reward_config, metadata)
    if not basic_check['eligible']:
        return basic_check

    # Usage limits
    usage_check = validate_usage_limit(user, reward_config)
    if not usage_check['within_limit']:
        return {
            'eligible': False,
            'error': usage_check['error'],
            'message': usage_check['message']
        }

    # Reward-specific conditions
    specific_check = _check_reward_specific_conditions(user, reward_type, reward_config, metadata)
    if not specific_check['eligible']:
        return specific_check

    return {
        'eligible': True,
        'message': 'User is eligible for this reward',
        'usage_info': usage_check
    }


def validate_usage_limit(user, reward_config) -> Dict[str, Any]:
    """
    Validates user's usage against reward limits.
    """
    from ..models import UserReward, RewardUsageLimit

    now = timezone.now()

    try:
        usage_limit = RewardUsageLimit.objects.get(user=user, reward_config=reward_config)
        limits = {
            'daily': usage_limit.daily_limit,
            'weekly': usage_limit.weekly_limit,
            'monthly': usage_limit.monthly_limit,
            'total': usage_limit.total_limit
        }
    except RewardUsageLimit.DoesNotExist:
        limits = {
            'daily': reward_config.daily_limit,
            'weekly': reward_config.weekly_limit,
            'monthly': reward_config.monthly_limit,
            'total': reward_config.total_limit
        }

    def usage_count_since(start_time):
        return UserReward.objects.filter(user=user, reward_config=reward_config, created_at__gte=start_time).count()

    if limits['daily'] is not None:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        count = usage_count_since(start)
        if count >= limits['daily']:
            return _limit_exceeded_response('DAILY', limits['daily'], count)

    if limits['weekly'] is not None:
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        count = usage_count_since(start)
        if count >= limits['weekly']:
            return _limit_exceeded_response('WEEKLY', limits['weekly'], count)

    if limits['monthly'] is not None:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count = usage_count_since(start)
        if count >= limits['monthly']:
            return _limit_exceeded_response('MONTHLY', limits['monthly'], count)

    if limits['total'] is not None:
        count = UserReward.objects.filter(user=user, reward_config=reward_config).count()
        if count >= limits['total']:
            return _limit_exceeded_response('TOTAL', limits['total'], count)

    return {
        'within_limit': True,
        'message': 'Usage within allowed limits'
    }


def validate_reward_conditions(user, conditions: Dict, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Validates additional conditions defined on a reward.
    """
    for cond, value in conditions.items():
        if cond == 'min_account_age_days':
            if (timezone.now() - user.created_at).days < value:
                return _error('MIN_ACCOUNT_AGE_NOT_MET', f'Account must be at least {value} days old')

        elif cond == 'email_verified':
            if value and not getattr(user, 'email_verified', False):
                return _error('EMAIL_NOT_VERIFIED', 'Email must be verified to receive this reward')

        elif cond == 'min_referrals':
            from referral_service.models import ReferralRelationship
            count = ReferralRelationship.objects.filter(referrer=user, is_active=True).count()
            if count < value:
                return _error('MIN_REFERRALS_NOT_MET', f'Must have at least {value} referrals')

        elif cond == 'max_previous_rewards':
            from ..models import UserReward
            count = UserReward.objects.filter(user=user).count()
            if count >= value:
                return _error('MAX_PREVIOUS_REWARDS_EXCEEDED', f'Maximum of {value} previous rewards allowed')

        elif cond == 'required_user_tier':
            user_tier = metadata.get('user_tier', 'basic') if metadata else 'basic'
            hierarchy = ['basic', 'silver', 'gold', 'platinum', 'diamond']
            if hierarchy.index(user_tier) < hierarchy.index(value):
                return _error('TIER_REQUIREMENT_NOT_MET', f'Must be {value} tier or higher')

        elif cond == 'min_transaction_amount':
            amount = metadata.get('transaction_amount', Decimal('0')) if metadata else Decimal('0')
            if amount < Decimal(str(value)):
                return _error('MIN_TRANSACTION_AMOUNT_NOT_MET', f'Minimum transaction amount of {value} required')

    return {'valid': True, 'message': 'All conditions met'}


def validate_reward_amount(amount: Decimal, reward_config, user_tier: str = 'basic') -> Dict[str, Any]:
    """
    Ensures reward amount falls within tier-specific, min/max config constraints.
    """
    if reward_config.min_amount and amount < reward_config.min_amount:
        return _error('AMOUNT_BELOW_MINIMUM', f'Amount must be at least {reward_config.min_amount}')

    if reward_config.max_amount and amount > reward_config.max_amount:
        return _error('AMOUNT_ABOVE_MAXIMUM', f'Amount cannot exceed {reward_config.max_amount}')

    tier_limits = {
        'basic': Decimal('100.00'),
        'silver': Decimal('250.00'),
        'gold': Decimal('500.00'),
        'platinum': Decimal('1000.00'),
        'diamond': Decimal('2500.00')
    }

    if amount > tier_limits.get(user_tier, Decimal('100.00')):
        return _error('TIER_LIMIT_EXCEEDED', f'Amount exceeds {user_tier} tier limit of {tier_limits[user_tier]}')

    return {'valid': True, 'message': 'Amount is valid'}


def _check_user_eligibility_criteria(user, reward_type, reward_config, metadata):
    if reward_type in ['registration', 'referral']:
        if not all([user.first_name, user.last_name, user.email]):
            return _error('INCOMPLETE_PROFILE', 'Complete profile required for this reward')

    if not user.is_active:
        return _error('ACCOUNT_INACTIVE', 'Account must be active to receive rewards')

    if reward_config.eligibility_criteria.get('require_email_verification', False):
        if not getattr(user, 'email_verified', False):
            return _error('EMAIL_VERIFICATION_REQUIRED', 'Email verification required for this reward')

    return {'eligible': True, 'message': 'Basic eligibility criteria met'}


def _check_reward_specific_conditions(user, reward_type, reward_config, metadata):
    now = timezone.now()

    if reward_type == 'registration':
        if (now - user.created_at) > timedelta(hours=24):
            return _error('REGISTRATION_WINDOW_EXPIRED', 'Registration rewards must be claimed within 24 hours')

    elif reward_type == 'first_payment':
        from payment_service.models import PaymentTransaction
        if PaymentTransaction.objects.filter(user=user, status='completed').count() > 1:
            return _error('NOT_FIRST_PAYMENT', 'This reward is only for first-time payments')

    elif reward_type == 'referral':
        if not metadata or 'referral_relationship_id' not in metadata:
            return _error('MISSING_REFERRAL_DATA', 'Referral relationship data required')

    return {'eligible': True, 'message': 'Reward-specific conditions met'}


def _error(error_code: str, message: str) -> Dict[str, Any]:
    return {'valid': False, 'eligible': False, 'within_limit': False, 'error': error_code, 'message': message}


def _limit_exceeded_response(limit_type: str, allowed: int, actual: int) -> Dict[str, Any]:
    return {
        'within_limit': False,
        'error': f'{limit_type}_LIMIT_EXCEEDED',
        'message': f'{limit_type.capitalize()} limit of {allowed} rewards exceeded',
        'current_usage': actual,
        'limit': allowed
    }
