from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.core.cache import cache
from typing import Dict, Optional, Any
from datetime import timedelta
from decimal import Decimal

from ..models import UserReward, RewardTransaction
# from payment_service.models import PaymentTransaction


def calculate_reward_metrics(user_id: Optional[str] = None, reward_type: Optional[str] = None, period: str = '30d') -> Dict[str, Any]:
    from reward_service.utils.period_utils import get_start_date_from_period
    from reward_service.utils.aggregation_utils import safe_sum, avg_per_user

    cache_key = f"reward_metrics_{user_id}_{reward_type}_{period}"
    if (cached := cache.get(cache_key)):
        return cached

    start_date = get_start_date_from_period(period)

    user_rewards = UserReward.objects.all()
    transactions = RewardTransaction.objects.all()

    if user_id:
        user_rewards = user_rewards.filter(user_id=user_id)
        transactions = transactions.filter(user_reward__user_id=user_id)

    if reward_type:
        user_rewards = user_rewards.filter(reward_config__reward_type=reward_type)
        transactions = transactions.filter(user_reward__reward_config__reward_type=reward_type)

    if start_date:
        transactions = transactions.filter(created_at__gte=start_date)

    total_users = user_rewards.count()
    total_earned = safe_sum(transactions.filter(transaction_type='earned'), 'amount')
    total_redeemed = safe_sum(transactions.filter(transaction_type='redeemed'), 'amount')
    total_outstanding = safe_sum(user_rewards, 'current_balance')

    transaction_data = {
        item['transaction_type']: item['count']
        for item in transactions.values('transaction_type').annotate(count=Count('id'))
    }

    avg_earned = avg_per_user(total_earned, total_users)
    avg_balance = avg_per_user(total_outstanding, total_users)
    redemption_rate = round((total_redeemed / total_earned * 100) if total_earned > 0 else 0, 2)

    reward_type_data = transactions.filter(transaction_type='earned')\
        .values('user_reward__reward_config__reward_type')\
        .annotate(count=Count('id'), total_amount=Sum('amount'))

    metrics = {
        'period': period,
        'total_users_with_rewards': total_users,
        'total_earned': float(total_earned),
        'total_redeemed': float(total_redeemed),
        'total_outstanding': float(total_outstanding),
        'avg_earned_per_user': float(avg_earned),
        'avg_balance_per_user': float(avg_balance),
        'redemption_rate': redemption_rate,
        'transaction_breakdown': transaction_data,
        'reward_type_breakdown': [
            {
                'reward_type': item['user_reward__reward_config__reward_type'],
                'count': item['count'],
                'total_amount': float(item['total_amount']),
            }
            for item in reward_type_data
        ]
    }

    cache.set(cache_key, metrics, 900)
    return metrics


def get_reward_analytics(start_date: Optional[timezone.datetime] = None, end_date: Optional[timezone.datetime] = None, group_by: str = 'day') -> Dict[str, Any]:
    from reward_service.utils.time_utils import group_transactions_by_period
    from reward_service.utils.formatting_utils import format_user_name

    start_date = start_date or (timezone.now() - timedelta(days=30))
    end_date = end_date or timezone.now()

    cache_key = f"reward_analytics_{start_date}_{end_date}_{group_by}"
    if (cached := cache.get(cache_key)):
        return cached

    transactions = RewardTransaction.objects.filter(created_at__range=(start_date, end_date))
    time_series = group_transactions_by_period(transactions, group_by)

    top_earners = transactions.filter(transaction_type='earned')\
        .values('user_reward__user__id', 'user_reward__user__first_name', 'user_reward__user__last_name')\
        .annotate(total_earned=Sum('amount'), transaction_count=Count('id'))\
        .order_by('-total_earned')[:10]

    reward_perf = transactions.filter(transaction_type='earned')\
        .values('user_reward__reward_config__reward_type')\
        .annotate(total_amount=Sum('amount'), transaction_count=Count('id'), unique_users=Count('user_reward__user', distinct=True))

    analytics = {
        'period': {
            'start_date': start_date,
            'end_date': end_date,
            'group_by': group_by,
        },
        'time_series': list(time_series),
        'top_earners': [
            {
                'user_id': str(item['user_reward__user__id']),
                'name': format_user_name(item),
                'total_earned': float(item['total_earned']),
                'transaction_count': item['transaction_count']
            }
            for item in top_earners
        ],
        'reward_performance': [
            {
                'reward_type': item['user_reward__reward_config__reward_type'],
                'total_amount': float(item['total_amount']),
                'transaction_count': item['transaction_count'],
                'unique_users': item['unique_users']
            }
            for item in reward_perf
        ]
    }

    cache.set(cache_key, analytics, 3600)
    return analytics


def calculate_reward_roi(campaign_id: Optional[str] = None, period: str = '30d') -> Dict[str, Any]:
    from reward_service.utils.period_utils import get_start_date_from_period
    from reward_service.utils.aggregation_utils import safe_sum, avg_per_user

    cache_key = f"reward_roi_{campaign_id}_{period}"
    if (cached := cache.get(cache_key)):
        return cached

    start_date = get_start_date_from_period(period)

    rewards = RewardTransaction.objects.filter(created_at__gte=start_date, transaction_type='earned')
    if campaign_id:
        rewards = rewards.filter(user_reward__reward_config__campaign_id=campaign_id)

    total_cost = safe_sum(rewards, 'amount')
    reward_user_ids = rewards.values_list('user_reward__user_id', flat=True).distinct()

    revenue = safe_sum(PaymentTransaction.objects.filter(
        user_id__in=reward_user_ids, status='completed', created_at__gte=start_date
    ), 'amount')

    net_benefit = revenue - total_cost
    roi = round((net_benefit / total_cost * 100) if total_cost > 0 else 0, 2)

    avg_reward = avg_per_user(total_cost, len(reward_user_ids))
    avg_revenue = avg_per_user(revenue, len(reward_user_ids))

    metrics = {
        'period': period,
        'campaign_id': campaign_id,
        'total_rewards_cost': float(total_cost),
        'revenue_from_reward_users': float(revenue),
        'net_benefit': float(net_benefit),
        'roi_percentage': roi,
        'reward_users_count': len(reward_user_ids),
        'avg_reward_per_user': float(avg_reward),
        'avg_revenue_per_user': float(avg_revenue)
    }

    cache.set(cache_key, metrics, 7200)
    return metrics


def get_user_reward_summary(user_id: str) -> Dict[str, Any]:
    from reward_service.utils.aggregation_utils import safe_sum
    from reward_service.utils.formatting_utils import format_transaction

    cache_key = f"user_reward_summary_{user_id}"
    if (cached := cache.get(cache_key)):
        return cached

    rewards = UserReward.objects.filter(user_id=user_id).select_related('reward_config')
    total_balance = safe_sum(rewards, 'current_balance')
    total_earned = safe_sum(rewards, 'total_earned')
    total_redeemed = safe_sum(rewards, 'total_redeemed')

    breakdown = [{
        'reward_type': reward.reward_config.reward_type,
        'reward_name': reward.reward_config.name,
        'current_balance': float(reward.current_balance),
        'total_earned': float(reward.total_earned),
        'total_redeemed': float(reward.total_redeemed),
        'last_updated': reward.last_updated
    } for reward in rewards]

    transactions = RewardTransaction.objects.filter(
        user_reward__user_id=user_id
    ).select_related('user_reward__reward_config').order_by('-created_at')[:10]

    summary = {
        'user_id': user_id,
        'total_balance': float(total_balance),
        'total_earned': float(total_earned),
        'total_redeemed': float(total_redeemed),
        'reward_breakdown': breakdown,
        'recent_transactions': [format_transaction(tx) for tx in transactions],
        'summary_generated_at': timezone.now()
    }

    cache.set(cache_key, summary, 600)
    return summary


def generate_reward_trends(period_days: int = 30, comparison_period_days: int = 30) -> Dict[str, Any]:
    from reward_service.utils.aggregation_utils import safe_aggregate_diff

    cache_key = f"reward_trends_{period_days}_{comparison_period_days}"
    if (cached := cache.get(cache_key)):
        return cached

    end = timezone.now()
    current_start = end - timedelta(days=period_days)
    compare_end = current_start
    compare_start = compare_end - timedelta(days=comparison_period_days)

    current = RewardTransaction.objects.filter(created_at__range=(current_start, end))
    compare = RewardTransaction.objects.filter(created_at__range=(compare_start, compare_end))

    current_metrics = current.aggregate(
        total_earned=Sum('amount', filter=Q(transaction_type='earned')),
        total_redeemed=Sum('amount', filter=Q(transaction_type='redeemed')),
        transaction_count=Count('id'),
        unique_users=Count('user_reward__user', distinct=True)
    )

    compare_metrics = compare.aggregate(
        total_earned=Sum('amount', filter=Q(transaction_type='earned')),
        total_redeemed=Sum('amount', filter=Q(transaction_type='redeemed')),
        transaction_count=Count('id'),
        unique_users=Count('user_reward__user', distinct=True)
    )

    trends = {
        'current_period': {
            'days': period_days,
            'total_earned': float(current_metrics['total_earned'] or 0),
            'total_redeemed': float(current_metrics['total_redeemed'] or 0),
            'transaction_count': current_metrics['transaction_count'],
            'unique_users': current_metrics['unique_users'],
        },
        'comparison_period': {
            'days': comparison_period_days,
            'total_earned': float(compare_metrics['total_earned'] or 0),
            'total_redeemed': float(compare_metrics['total_redeemed'] or 0),
            'transaction_count': compare_metrics['transaction_count'],
            'unique_users': compare_metrics['unique_users'],
        },
        'changes': {
            'earned_change': safe_aggregate_diff(current_metrics['total_earned'], compare_metrics['total_earned']),
            'redeemed_change': safe_aggregate_diff(current_metrics['total_redeemed'], compare_metrics['total_redeemed']),
            'transaction_change': safe_aggregate_diff(current_metrics['transaction_count'], compare_metrics['transaction_count']),
            'user_change': safe_aggregate_diff(current_metrics['unique_users'], compare_metrics['unique_users']),
        }
    }

    cache.set(cache_key, trends, 3600)
    return trends
