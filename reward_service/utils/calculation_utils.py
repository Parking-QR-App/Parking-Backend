from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.utils import timezone
from typing import Dict, Optional, Any, List

CURRENCY_DECIMALS = Decimal('0.01')


def calculate_reward_amount(
    reward_type: str,
    base_amount: Decimal,
    user_tier: str = 'basic',
    multiplier: Optional[Decimal] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Calculate the final reward amount based on tier, type, and optional multipliers.

    Supported reward_type: 'registration', 'referral', 'payment'

    Returns:
        {
            'amount': Decimal,
            'calculation_breakdown': Dict,
            'currency': str
        }
    """
    assert reward_type in ['registration', 'referral', 'payment'], "Unsupported reward_type"
    assert isinstance(base_amount, Decimal), "base_amount must be Decimal"

    metadata = metadata or {}
    multiplier = multiplier or Decimal('1.0')

    tier_multipliers = {
        'basic': Decimal('1.0'),
        'silver': Decimal('1.2'),
        'gold': Decimal('1.5'),
        'platinum': Decimal('2.0'),
        'diamond': Decimal('2.5')
    }

    tier_multiplier = tier_multipliers.get(user_tier, Decimal('1.0'))

    amount = base_amount * tier_multiplier * multiplier

    # Apply reward-type specific business rules
    if reward_type == 'registration':
        max_reward = getattr(settings, 'MAX_REGISTRATION_REWARD', Decimal('100.00'))
        amount = min(amount, max_reward)

    elif reward_type == 'referral':
        referral_count = metadata.get('referral_count', 0)
        if referral_count > 10:
            bonus_multiplier = Decimal('1.1')
            amount *= bonus_multiplier
            metadata['bonus_multiplier'] = bonus_multiplier

    final_amount = amount.quantize(CURRENCY_DECIMALS, rounding=ROUND_HALF_UP)

    return {
        'amount': final_amount,
        'calculation_breakdown': {
            'base_amount': base_amount,
            'user_tier': user_tier,
            'tier_multiplier': tier_multiplier,
            'special_multiplier': multiplier,
            'final_amount': final_amount,
            **metadata
        },
        'currency': 'USD'  # TODO: Make configurable
    }


def calculate_cashback(
    transaction_amount: Decimal,
    cashback_percentage: Decimal,
    max_cashback: Optional[Decimal] = None,
    min_transaction: Optional[Decimal] = None
) -> Dict[str, Any]:
    """
    Calculate cashback from a transaction.
    """
    assert isinstance(transaction_amount, Decimal), "transaction_amount must be Decimal"

    if min_transaction and transaction_amount < min_transaction:
        return {
            'eligible': False,
            'reason': 'BELOW_MINIMUM_TRANSACTION',
            'cashback_amount': Decimal('0.00'),
            'min_required': min_transaction,
            'transaction_amount': transaction_amount
        }

    cashback_amount = (transaction_amount * cashback_percentage / Decimal('100'))

    capped = False
    if max_cashback and cashback_amount > max_cashback:
        cashback_amount = max_cashback
        capped = True

    cashback_amount = cashback_amount.quantize(CURRENCY_DECIMALS, rounding=ROUND_HALF_UP)

    return {
        'eligible': True,
        'cashback_amount': cashback_amount,
        'cashback_percentage': cashback_percentage,
        'transaction_amount': transaction_amount,
        'max_cashback': max_cashback,
        'capped': capped,
        'effective_percentage': (
            (cashback_amount / transaction_amount * Decimal('100'))
            if transaction_amount > 0 else Decimal('0.00')
        )
    }


def calculate_tiered_reward(
    base_amount: Decimal,
    tier_config: Dict[str, Decimal],
    user_activity_score: int
) -> Dict[str, Any]:
    """
    Calculate a reward using an activity-score based tier system.
    """
    if user_activity_score >= 1000:
        tier = 'diamond'
    elif user_activity_score >= 500:
        tier = 'platinum'
    elif user_activity_score >= 200:
        tier = 'gold'
    elif user_activity_score >= 50:
        tier = 'silver'
    else:
        tier = 'basic'

    multiplier = tier_config.get(tier, Decimal('1.0'))
    final_amount = (base_amount * multiplier).quantize(CURRENCY_DECIMALS, rounding=ROUND_HALF_UP)

    return {
        'tier': tier,
        'base_amount': base_amount,
        'multiplier': multiplier,
        'final_amount': final_amount,
        'activity_score': user_activity_score
    }


def calculate_progressive_bonus(
    referral_count: int,
    base_reward: Decimal,
    progression_config: Optional[Dict[int, Decimal]] = None
) -> Dict[str, Any]:
    """
    Calculate reward bonus based on progressive referral milestones.
    """
    config = progression_config or {
        5: Decimal('0.10'),
        10: Decimal('0.25'),
        25: Decimal('0.50'),
        50: Decimal('1.00'),
        100: Decimal('2.00')
    }

    applicable_bonus = Decimal('0.00')
    milestone_reached = 0

    for milestone in sorted(config.keys(), reverse=True):
        if referral_count >= milestone:
            applicable_bonus = config[milestone]
            milestone_reached = milestone
            break

    bonus_amount = base_reward * applicable_bonus
    final_amount = (base_reward + bonus_amount).quantize(CURRENCY_DECIMALS, rounding=ROUND_HALF_UP)

    # Next milestone
    upcoming = [(m, b) for m, b in sorted(config.items()) if m > referral_count]
    next_milestone, next_bonus = upcoming[0] if upcoming else (None, None)

    return {
        'referral_count': referral_count,
        'base_reward': base_reward,
        'applicable_bonus_percent': applicable_bonus * 100,
        'bonus_amount': bonus_amount,
        'final_amount': final_amount,
        'milestone_reached': milestone_reached,
        'next_milestone': next_milestone,
        'next_bonus_percent': next_bonus * 100 if next_bonus else None,
        'referrals_to_next_milestone': (
            next_milestone - referral_count if next_milestone else None
        )
    }


def calculate_call_credits(
    reward_amount: Decimal,
    credit_conversion_rate: Decimal,
    bonus_credits: int = 0
) -> Dict[str, Any]:
    """
    Convert monetary reward into platform-specific call credits.
    """
    assert credit_conversion_rate > 0, "conversion rate must be positive"

    base_credits = int((reward_amount * credit_conversion_rate).to_integral_value(ROUND_HALF_UP))
    total_credits = base_credits + bonus_credits
    equivalent_value = Decimal(total_credits) / credit_conversion_rate

    return {
        'reward_amount': reward_amount,
        'base_credits': base_credits,
        'bonus_credits': bonus_credits,
        'total_credits': total_credits,
        'conversion_rate': credit_conversion_rate,
        'equivalent_value': equivalent_value.quantize(CURRENCY_DECIMALS)
    }


def apply_seasonal_multiplier(
    base_amount: Decimal,
    current_date: Optional[timezone.datetime] = None
) -> Dict[str, Any]:
    """
    Boost rewards based on seasonal promotions.
    """
    current_date = current_date or timezone.now()
    month = current_date.month

    seasonal_multipliers = {
        12: Decimal('1.5'),  # December
        1: Decimal('1.3'),   # January
        3: Decimal('1.2'),   # March
        6: Decimal('1.1'),   # June
        11: Decimal('1.4'),  # November
    }

    multiplier = seasonal_multipliers.get(month, Decimal('1.0'))
    final_amount = (base_amount * multiplier).quantize(CURRENCY_DECIMALS, rounding=ROUND_HALF_UP)

    return {
        'base_amount': base_amount,
        'season': _get_season_name(month),
        'seasonal_multiplier': multiplier,
        'final_amount': final_amount,
        'is_promotional_period': multiplier > Decimal('1.0')
    }


def calculate_compound_rewards(
    rewards_list: List[Decimal],
    compound_rate: Decimal = Decimal('0.05')
) -> Dict[str, Any]:
    """
    Apply compound bonus when multiple reward types are granted together.
    """
    assert all(isinstance(r, Decimal) for r in rewards_list), "All rewards must be Decimal"

    base_total = sum(rewards_list)

    if len(rewards_list) <= 1:
        return {
            'base_total': base_total,
            'compound_bonus': Decimal('0.00'),
            'final_total': base_total,
            'compound_rate': compound_rate
        }

    compound_multiplier = (Decimal('1.0') + compound_rate) ** (len(rewards_list) - 1)
    compound_bonus = base_total * (compound_multiplier - Decimal('1.0'))
    final_total = (base_total + compound_bonus).quantize(CURRENCY_DECIMALS)

    return {
        'base_total': base_total,
        'compound_bonus': compound_bonus.quantize(CURRENCY_DECIMALS),
        'final_total': final_total,
        'compound_rate': compound_rate,
        'compound_multiplier': compound_multiplier,
        'reward_count': len(rewards_list)
    }


def _get_season_name(month: int) -> str:
    """Return human-readable season name for a given month."""
    if month in [12, 1, 2]:
        return 'Winter'
    elif month in [3, 4, 5]:
        return 'Spring'
    elif month in [6, 7, 8]:
        return 'Summer'
    return 'Fall'
