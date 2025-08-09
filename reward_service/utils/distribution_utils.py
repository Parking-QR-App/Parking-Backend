from django.db import transaction
from django.utils import timezone
from django.core.cache import cache
from decimal import Decimal
from typing import Dict, Optional, Any, List

from ..models import UserReward, RewardTransaction, RewardConfiguration
from .validation_utils import (
    validate_reward_eligibility,
    validate_reward_amount,
)
from .calculation_utils import (
    update_user_reward_balances,
    ensure_sufficient_balance,
    calculate_converted_credits,
)
from .configuration_utils import get_reward_conversion_rate


def distribute_reward(
    user,
    reward_config: RewardConfiguration,
    amount: Decimal,
    metadata: Optional[Dict] = None,
    source_transaction_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Distribute a reward to a user.
    """
    # Step 1: Validations
    eligibility = validate_reward_eligibility(user, reward_config.reward_type, reward_config, metadata)
    if not eligibility["eligible"]:
        return {
            "success": False,
            "error": eligibility["error"],
            "message": eligibility["message"],
        }

    amount_check = validate_reward_amount(amount, reward_config)
    if not amount_check["valid"]:
        return {
            "success": False,
            "error": amount_check["error"],
            "message": amount_check["message"],
        }

    try:
        with transaction.atomic():
            user_reward, _ = UserReward.objects.get_or_create(
                user=user,
                reward_config=reward_config,
                defaults={
                    "current_balance": Decimal("0.00"),
                    "total_earned": Decimal("0.00"),
                    "total_redeemed": Decimal("0.00"),
                    "metadata": metadata or {},
                }
            )

            reward_transaction = RewardTransaction.objects.create(
                user_reward=user_reward,
                transaction_type="earned",
                amount=amount,
                description=f"Reward earned: {reward_config.name}",
                metadata=metadata or {},
                source_transaction_id=source_transaction_id,
            )

            update_user_reward_balances(user_reward, "earned", amount)

            distribution_details = _handle_reward_type_specific_logic(
                user, reward_config, amount, user_reward, metadata
            )

            _clear_reward_caches(user.id, reward_config.id)

            return {
                "success": True,
                "user_reward": user_reward,
                "transaction": reward_transaction,
                "amount_distributed": amount,
                "new_balance": user_reward.current_balance,
                "additional_info": distribution_details,
                "message": f"Successfully distributed {amount} {reward_config.reward_type} reward",
            }

    except Exception as e:
        return {
            "success": False,
            "error": "DISTRIBUTION_FAILED",
            "message": f"Failed to distribute reward: {str(e)}",
        }


def redeem_reward(
    user,
    reward_config: RewardConfiguration,
    redemption_amount: Decimal,
    redemption_type: str,
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Redeem rewards for specific benefits.
    """
    try:
        user_reward = UserReward.objects.select_for_update().get(user=user, reward_config=reward_config)

        if not ensure_sufficient_balance(user_reward.current_balance, redemption_amount):
            return {
                "success": False,
                "error": "INSUFFICIENT_BALANCE",
                "message": f"Insufficient balance. Available: {user_reward.current_balance}, Required: {redemption_amount}",
            }

        txn_result = process_reward_transaction(
            user_reward=user_reward,
            transaction_type="redeemed",
            amount=redemption_amount,
            description=f"Redeemed for {redemption_type}",
            metadata=metadata
        )

        if not txn_result["success"]:
            return txn_result

        redemption_details = _handle_redemption_type(
            user, redemption_amount, redemption_type, metadata
        )

        _clear_reward_caches(user.id, reward_config.id)

        return {
            "success": True,
            "redemption_type": redemption_type,
            "amount_redeemed": redemption_amount,
            "remaining_balance": user_reward.current_balance,
            "redemption_details": redemption_details,
            "transaction": txn_result["transaction"],
            "message": f"Successfully redeemed {redemption_amount} for {redemption_type}",
        }

    except UserReward.DoesNotExist:
        return {
            "success": False,
            "error": "REWARD_NOT_FOUND",
            "message": "No reward balance found for this user and reward type",
        }
    except Exception as e:
        return {
            "success": False,
            "error": "REDEMPTION_FAILED",
            "message": f"Failed to redeem reward: {str(e)}",
        }


def process_reward_transaction(
    user_reward: UserReward,
    transaction_type: str,
    amount: Decimal,
    description: str,
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Record and apply a reward transaction.
    """
    try:
        with transaction.atomic():
            txn = RewardTransaction.objects.create(
                user_reward=user_reward,
                transaction_type=transaction_type,
                amount=amount,
                description=description,
                metadata=metadata or {}
            )

            update_user_reward_balances(user_reward, transaction_type, amount)

            return {
                "success": True,
                "transaction": txn,
                "new_balance": user_reward.current_balance,
                "message": "Transaction processed successfully"
            }

    except Exception as e:
        return {
            "success": False,
            "error": "TRANSACTION_FAILED",
            "message": f"Failed to process transaction: {str(e)}"
        }


def bulk_distribute_rewards(rewards_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Bulk reward distribution utility.
    """
    success, failure = [], []

    for reward in rewards_data:
        try:
            result = distribute_reward(
                user=reward["user"],
                reward_config=reward["reward_config"],
                amount=reward["amount"],
                metadata=reward.get("metadata"),
                source_transaction_id=reward.get("source_transaction_id")
            )

            if result["success"]:
                success.append({
                    "user_id": str(reward["user"].id),
                    "transaction_id": str(result["transaction"].id),
                    "amount": reward["amount"],
                })
            else:
                failure.append({
                    "user_id": str(reward["user"].id),
                    "error": result["error"],
                    "message": result["message"],
                })

        except Exception as e:
            failure.append({
                "user_id": str(reward.get("user", {}).get("id", "unknown")),
                "error": "UNEXPECTED_ERROR",
                "message": str(e),
            })

    return {
        "total_processed": len(rewards_data),
        "successful_count": len(success),
        "failed_count": len(failure),
        "successful_distributions": success,
        "failed_distributions": failure
    }


def _handle_reward_type_specific_logic(
    user,
    reward_config: RewardConfiguration,
    amount: Decimal,
    user_reward: UserReward,
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Handles reward-type-specific logic (e.g., apply call credits).
    """
    if reward_config.reward_type == "call_credits":
        from payment_service.models import CallCredit
        credits = calculate_converted_credits(amount, reward_config.reward_type)
        call_credit, _ = CallCredit.objects.get_or_create(user=user, defaults={
            "credits_balance": 0,
            "total_purchased": 0
        })
        call_credit.credits_balance += credits
        call_credit.save()
        return {"credits_added": credits, "new_credits_balance": call_credit.credits_balance}

    elif reward_config.reward_type == "cashback":
        return {
            "cashback_amount": amount,
            "cashback_percentage": metadata.get("cashback_percentage", 0) if metadata else 0,
        }

    return {}


def _handle_redemption_type(
    user,
    amount: Decimal,
    redemption_type: str,
    metadata: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Handle redemption side-effects (call credits, cashback, etc).
    """
    if redemption_type == "call_credits":
        from payment_service.models import CallCredit
        credits = calculate_converted_credits(amount, "call_credits")
        call_credit, _ = CallCredit.objects.get_or_create(user=user, defaults={
            "credits_balance": 0,
            "total_purchased": 0
        })
        call_credit.credits_balance += credits
        call_credit.save()
        return {"credits_added": credits, "conversion_rate": get_reward_conversion_rate("call_credits")}

    elif redemption_type == "cashback":
        return {"cashback_amount": amount, "processing_time": "1-3 business days"}

    return {}


def _clear_reward_caches(user_id: str, reward_config_id: str):
    """
    Clear all related cache entries for a user-reward pair.
    """
    for key in [
        f"pending_rewards_{user_id}",
        f"user_rewards_{user_id}",
        f"reward_metrics_{user_id}",
        f"reward_balance_{user_id}_{reward_config_id}"
    ]:
        cache.delete(key)
