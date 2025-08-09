from django.db import transaction
from decimal import Decimal
from typing import Dict, List, Optional, Any

from ..models import RewardConfiguration, UserReward
from ..utils import (
    distribution_utils,
    validation_utils,
    calculation_utils,
    configuration_utils
)

class RewardDistributionService:
    """
    Handles all reward distribution operations with atomic execution.
    Enforces validation before distribution and systematically uses all distribution utils.
    """
    
    @transaction.atomic
    def distribute_single_reward(
        self,
        user: Any,
        reward_config: RewardConfiguration,
        amount: Decimal,
        metadata: Optional[Dict] = None,
        source_transaction_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Distributes a single reward after validation.
        
        Utils used:
        - validation_utils.validate_reward_eligibility
        - validation_utils.validate_reward_amount
        - distribution_utils.distribute_reward
        - calculation_utils.calculate_reward_amount (if amount needs calculation)
        """
        # Validate eligibility
        eligibility = validation_utils.validate_reward_eligibility(
            user,
            reward_config.reward_type,
            reward_config,
            metadata
        )
        if not eligibility['eligible']:
            return {
                'success': False,
                **eligibility
            }
            
        # Validate amount
        amount_check = validation_utils.validate_reward_amount(amount, reward_config, getattr(user, 'tier', 'basic'))
        if not amount_check['valid']:
            return {
                'success': False,
                **amount_check
            }
            
        # Distribute
        return distribution_utils.distribute_reward(
            user=user,
            reward_config=reward_config,
            amount=amount,
            metadata=metadata,
            source_transaction_id=source_transaction_id
        )

    @transaction.atomic
    def distribute_bulk_rewards(
        self,
        rewards_data: List[Dict[str, Any]],
        batch_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Distributes rewards in bulk with individual validation per reward.
        
        Utils used:
        - distribution_utils.bulk_distribute_rewards (core distribution)
        - validation_utils.validate_reward_eligibility (per user)
        - validation_utils.validate_reward_amount (per reward)
        """
        validated_data = []
        
        for reward in rewards_data:
            user = reward['user']
            config = reward['reward_config']
            amount = reward['amount']
            
            # Validate each reward
            eligibility = validation_utils.validate_reward_eligibility(
                user,
                config.reward_type,
                config,
                reward.get('metadata')
            )
            
            if not eligibility['eligible']:
                continue
                
            amount_check = validation_utils.validate_reward_amount(
                amount,
                config,
                getattr(user, 'tier', 'basic')
            )
            
            if not amount_check['valid']:
                continue
                
            validated_data.append(reward)
            
        # Process validated rewards
        return distribution_utils.bulk_distribute_rewards(validated_data)

    def process_reward_transaction(
        self,
        user_reward: UserReward,
        transaction_type: str,
        amount: Decimal,
        description: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Processes a reward transaction with balance updates.
        
        Utils used:
        - distribution_utils.process_reward_transaction
        - validation_utils.validate_reward_amount
        """
        # Validate amount
        amount_check = validation_utils.validate_reward_amount(
            amount,
            user_reward.reward_config,
            getattr(user_reward.user, 'tier', 'basic')
        )
        
        if not amount_check['valid']:
            return {
                'success': False,
                **amount_check
            }
            
        return distribution_utils.process_reward_transaction(
            user_reward=user_reward,
            transaction_type=transaction_type,
            amount=amount,
            description=description,
            metadata=metadata
        )