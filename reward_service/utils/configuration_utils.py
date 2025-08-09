from django.core.cache import cache
from django.db import models
from django.utils import timezone
from typing import Dict, Optional, Any, List
from decimal import Decimal

# Constants
CACHE_TIMEOUTS = {
    "config": 3600,           # 1 hour
    "active_configs": 1800,   # 30 mins
    "effectiveness": 7200     # 2 hours
}

TIER_MULTIPLIERS = {
    'basic': 1.0,
    'silver': 1.2,
    'gold': 1.5,
    'platinum': 2.0,
    'diamond': 2.5
}

# Public Functions

def get_reward_config(
    reward_type: str,
    user_tier: Optional[str] = None,
    campaign_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    from ..models import RewardConfiguration

    cache_key = f"reward_config_{reward_type}_{user_tier}_{campaign_id}"
    if cached := cache.get(cache_key):
        return cached

    now = timezone.now()
    query = RewardConfiguration.objects.filter(
        reward_type=reward_type,
        is_active=True,
        valid_from__lte=now
    ).filter(
        models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=now)
    )

    if campaign_id:
        from campaign_service.models import Campaign
        try:
            campaign = Campaign.objects.get(id=campaign_id)
            query = query.filter(campaign=campaign)
        except Campaign.DoesNotExist:
            return None

    config = query.order_by('-created_at').first()
    if not config:
        return None

    config_data = _serialize_config(config)
    if user_tier:
        config_data = _apply_tier_modifications(config_data, user_tier)

    cache.set(cache_key, config_data, CACHE_TIMEOUTS["config"])
    return config_data


def get_active_reward_configs(
    reward_types: Optional[List[str]] = None,
    include_campaign_configs: bool = True
) -> List[Dict[str, Any]]:
    from ..models import RewardConfiguration

    cache_key = f"active_configs_{reward_types}_{include_campaign_configs}"
    if cached := cache.get(cache_key):
        return cached

    now = timezone.now()
    query = RewardConfiguration.objects.filter(
        is_active=True,
        valid_from__lte=now
    ).filter(
        models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=now)
    )

    if reward_types:
        query = query.filter(reward_type__in=reward_types)
    if not include_campaign_configs:
        query = query.filter(campaign__isnull=True)

    configs = [_serialize_config(cfg) for cfg in query.order_by('reward_type', '-created_at')]
    cache.set(cache_key, configs, CACHE_TIMEOUTS["active_configs"])
    return configs


def update_reward_config(config_id: str, updates: Dict[str, Any], updated_by=None) -> Dict[str, Any]:
    from ..models import RewardConfiguration

    try:
        config = RewardConfiguration.objects.get(id=config_id)

        validation = _validate_config_updates(config, updates)
        if not validation["valid"]:
            return {**validation, "success": False}

        for field, value in updates.items():
            if hasattr(config, field):
                setattr(config, field, value)

        config.save()
        _clear_config_caches(config.reward_type)

        return {"success": True, "updated_config": config, "message": "Configuration updated successfully"}

    except RewardConfiguration.DoesNotExist:
        return {"success": False, "error": "CONFIG_NOT_FOUND", "message": "Configuration not found"}
    except Exception as e:
        return {"success": False, "error": "UPDATE_FAILED", "message": str(e)}


def create_reward_config(config_data: Dict[str, Any], created_by=None) -> Dict[str, Any]:
    from ..models import RewardConfiguration

    validation = _validate_new_config_data(config_data)
    if not validation["valid"]:
        return {**validation, "success": False}

    try:
        config = RewardConfiguration.objects.create(**config_data)
        _clear_config_caches(config.reward_type)
        return {"success": True, "config": config, "message": "Configuration created"}
    except Exception as e:
        return {"success": False, "error": "CREATION_FAILED", "message": str(e)}


def calculate_config_effectiveness(config_id: str) -> Dict[str, Any]:
    from ..models import RewardConfiguration, UserReward, RewardTransaction

    cache_key = f"config_effectiveness_{config_id}"
    if cached := cache.get(cache_key):
        return cached

    try:
        config = RewardConfiguration.objects.get(id=config_id)
        total_users = UserReward.objects.filter(reward_config=config).count()
        total_txns = RewardTransaction.objects.filter(user_reward__reward_config=config)

        total_distributed = total_txns.filter(transaction_type='earned') \
            .aggregate(sum=models.Sum('amount'))['sum'] or Decimal('0.00')
        total_redeemed = total_txns.filter(transaction_type='redeemed') \
            .aggregate(sum=models.Sum('amount'))['sum'] or Decimal('0.00')

        redemption_rate = (total_redeemed / total_distributed * 100) if total_distributed > 0 else 0
        avg_per_user = (total_distributed / total_users) if total_users > 0 else Decimal('0.00')

        metrics = {
            "config_id": config_id,
            "config_name": config.name,
            "total_users": total_users,
            "total_transactions": total_txns.count(),
            "total_distributed": float(total_distributed),
            "total_redeemed": float(total_redeemed),
            "redemption_rate": round(float(redemption_rate), 2),
            "avg_reward_per_user": float(avg_per_user),
            "config_created": config.created_at,
            "days_active": (timezone.now() - config.created_at).days
        }

        cache.set(cache_key, metrics, CACHE_TIMEOUTS["effectiveness"])
        return metrics

    except RewardConfiguration.DoesNotExist:
        return {"error": "CONFIG_NOT_FOUND"}


def clone_reward_config(
    source_config_id: str,
    new_name: str,
    modifications: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    from ..models import RewardConfiguration

    try:
        source = RewardConfiguration.objects.get(id=source_config_id)
        new_data = {
            "name": new_name,
            "reward_type": source.reward_type,
            "value_per_unit": source.value_per_unit,
            "min_amount": source.min_amount,
            "max_amount": source.max_amount,
            "daily_limit": source.daily_limit,
            "weekly_limit": source.weekly_limit,
            "monthly_limit": source.monthly_limit,
            "total_limit": source.total_limit,
            "eligibility_criteria": source.eligibility_criteria.copy(),
            "configuration_data": source.configuration_data.copy(),
            "valid_from": timezone.now(),
            "is_active": False
        }

        if modifications:
            new_data.update(modifications)

        new_config = RewardConfiguration.objects.create(**new_data)
        return {"success": True, "new_config": new_config, "message": "Cloned successfully"}

    except RewardConfiguration.DoesNotExist:
        return {"success": False, "error": "SOURCE_CONFIG_NOT_FOUND", "message": "Source config missing"}
    except Exception as e:
        return {"success": False, "error": "CLONING_FAILED", "message": str(e)}


# Internal Utilities

def _apply_tier_modifications(config_data: Dict[str, Any], user_tier: str) -> Dict[str, Any]:
    multiplier = TIER_MULTIPLIERS.get(user_tier, 1.0)

    if config_data.get('max_amount'):
        config_data['max_amount'] = config_data['max_amount'] * Decimal(str(multiplier))

    if user_tier in ['platinum', 'diamond']:
        for limit in ['daily_limit', 'monthly_limit']:
            if config_data.get(limit):
                config_data[limit] = int(config_data[limit] * multiplier)

    return config_data


def _validate_config_updates(config, updates: Dict[str, Any]) -> Dict[str, Any]:
    if 'value_per_unit' in updates and updates['value_per_unit'] <= 0:
        return {"valid": False, "error": "INVALID_VALUE_PER_UNIT", "message": "Value must be positive"}

    if 'valid_from' in updates and 'valid_until' in updates:
        if updates['valid_until'] <= updates['valid_from']:
            return {"valid": False, "error": "INVALID_DATE_RANGE", "message": "End date must follow start date"}

    return {"valid": True}


def _validate_new_config_data(data: Dict[str, Any]) -> Dict[str, Any]:
    required = ['name', 'reward_type', 'value_per_unit']
    for field in required:
        if field not in data:
            return {"valid": False, "error": "MISSING_FIELD", "message": f"{field} is required"}
    return {"valid": True}


def _serialize_config(config) -> Dict[str, Any]:
    return {
        "id": str(config.id),
        "name": config.name,
        "reward_type": config.reward_type,
        "value_per_unit": config.value_per_unit,
        "min_amount": config.min_amount,
        "max_amount": config.max_amount,
        "eligibility_criteria": config.eligibility_criteria,
        "configuration_data": config.configuration_data,
        "daily_limit": config.daily_limit,
        "weekly_limit": config.weekly_limit,
        "monthly_limit": config.monthly_limit,
        "total_limit": config.total_limit,
        "valid_from": config.valid_from,
        "valid_until": config.valid_until,
        "campaign_id": str(config.campaign.id) if config.campaign else None
    }


def _clear_config_caches(reward_type: str):
    # NOTE: In production, use Redis SCAN/MATCH to pattern-clear
    # Here we clear hardcoded patterns
    keys = [
        f"reward_config_{reward_type}_basic_None",
        f"reward_config_{reward_type}_silver_None",
        f"reward_config_{reward_type}_gold_None",
        f"reward_config_{reward_type}_platinum_None",
        f"reward_config_{reward_type}_diamond_None",
        f"active_configs_None_True"
    ]
    for key in keys:
        cache.delete(key)
