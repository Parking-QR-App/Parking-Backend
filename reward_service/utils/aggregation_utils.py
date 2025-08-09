from decimal import Decimal
from typing import List, Optional
from reward_service.models import RewardTransaction


def safe_sum(values: List[Optional[Decimal]]) -> Decimal:
    """
    Returns the sum of Decimal values, ignoring None.
    """
    return sum((v or Decimal("0.00")) for v in values)


def avg_per_user(total: Decimal, user_count: int) -> float:
    """
    Returns average value per user, safely.
    """
    if user_count == 0:
        return 0.0
    return float(total / Decimal(user_count))


def safe_aggregate_diff(value1: Optional[Decimal], value2: Optional[Decimal]) -> Decimal:
    """
    Returns a safe difference between two values.
    """
    return (value1 or Decimal("0.00")) - (value2 or Decimal("0.00"))
