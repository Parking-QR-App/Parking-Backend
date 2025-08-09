from typing import Union
from reward_service.models import RewardTransaction


def format_user_name(first_name: str, last_name: str) -> str:
    """
    Returns a clean full name for display purposes.
    """
    return f"{first_name.strip().title()} {last_name.strip().title()}"


def format_transaction(txn: RewardTransaction) -> dict:
    """
    Formats a reward transaction object into a serializable dictionary.
    """
    return {
        "id": str(txn.id),
        "amount": float(txn.amount),
        "type": txn.transaction_type,
        "timestamp": txn.timestamp.isoformat(),
        "description": txn.description or "",
    }
