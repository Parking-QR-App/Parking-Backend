from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Literal

from reward_service.models import RewardTransaction


def group_transactions_by_period(
    transactions: List[RewardTransaction],
    period: Literal["daily", "weekly", "monthly"]
) -> Dict[str, List[RewardTransaction]]:
    """
    Groups transactions by the specified period (day/week/month).
    """
    grouped = defaultdict(list)
    for txn in transactions:
        dt = txn.timestamp
        if period == "daily":
            key = dt.strftime("%Y-%m-%d")
        elif period == "weekly":
            key = f"{dt.year}-W{dt.isocalendar()[1]}"
        elif period == "monthly":
            key = dt.strftime("%Y-%m")
        else:
            continue
        grouped[key].append(txn)
    return dict(grouped)
