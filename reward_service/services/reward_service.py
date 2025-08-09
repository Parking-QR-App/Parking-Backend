from django.db import transaction
from decimal import Decimal
from typing import Dict, Optional, Any, List
from django.utils import timezone

from ..utils import (
    calculation_utils,
    validation_utils,
    distribution_utils,
    configuration_utils,
    analytics_utils
)

class RewardService:
    """
    Core reward service handling all reward operations with strict validation flows.
    Enforces validation before any action and systematically uses all utility functions.
    """
    
    def calculate_potential_reward(
        self,
        user: Any,
        reward_type: str,
        base_amount: Decimal,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Calculates potential reward amount with all modifiers applied.
        
        Utils used:
        - calculation_utils.calculate_reward_amount (main calculation)
        - calculation_utils.apply_seasonal_multiplier (seasonal boosts)
        - calculation_utils.calculate_compound_rewards (if multiple rewards)
        - validation_utils.validate_reward_amount (amount validation)
        
        Validation chain:
        1. Validate reward amount is positive
        2. Validate against config min/max
        3. Validate against user tier limits
        """
        if not metadata:
            metadata = {}
            
        # Get active config first
        config = configuration_utils.get_reward_config(reward_type, user.tier)
        if not config:
            return {
                'success': False,
                'error': 'NO_ACTIVE_CONFIG',
                'message': f'No active configuration for {reward_type} rewards'
            }
        
        # Base calculation
        base_result = calculation_utils.calculate_reward_amount(
            reward_type=reward_type,
            base_amount=base_amount,
            user_tier=user.tier,
            metadata=metadata
        )
        
        # Apply seasonal multiplier
        seasonal_result = calculation_utils.apply_seasonal_multiplier(base_result['amount'])
        if seasonal_result['is_promotional_period']:
            metadata['seasonal_multiplier'] = seasonal_result['seasonal_multiplier']
            base_result['amount'] = seasonal_result['final_amount']
            base_result['calculation_breakdown']['seasonal_multiplier'] = seasonal_result['seasonal_multiplier']
        
        # Validate final amount
        amount_validation = validation_utils.validate_reward_amount(
            base_result['amount'],
            config,
            user.tier
        )
        if not amount_validation['valid']:
            return {
                'success': False,
                **amount_validation
            }
            
        return {
            'success': True,
            'calculated_reward': base_result,
            'config': config
        }

    @transaction.atomic
    def grant_reward(
        self,
        user: Any,
        reward_type: str,
        amount: Decimal,
        trigger_event: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Grants a reward to a user after full validation.
        
        Utils used:
        - validation_utils.validate_reward_eligibility (top-level check)
        - validation_utils.validate_usage_limit (usage limits)
        - validation_utils.validate_reward_conditions (specific conditions)
        - distribution_utils.distribute_reward (actual distribution)
        - configuration_utils.get_reward_config (config lookup)
        
        Validation chain:
        1. Validate user eligibility
        2. Validate reward conditions
        3. Validate usage limits
        4. Validate amount
        """
        if not metadata:
            metadata = {}
            
        config = configuration_utils.get_reward_config(reward_type, user.tier)
        if not config:
            return {
                'success': False,
                'error': 'NO_ACTIVE_CONFIG',
                'message': f'No active configuration for {reward_type} rewards'
            }
        
        # Full eligibility validation
        eligibility = validation_utils.validate_reward_eligibility(user, reward_type, config, metadata)
        if not eligibility['eligible']:
            return {
                'success': False,
                **eligibility
            }
            
        # Conditions validation
        conditions_check = validation_utils.validate_reward_conditions(user, config.eligibility_criteria, metadata)
        if not conditions_check['valid']:
            return {
                'success': False,
                **conditions_check
            }
            
        # Amount validation
        amount_check = validation_utils.validate_reward_amount(amount, config, user.tier)
        if not amount_check['valid']:
            return {
                'success': False,
                **amount_check
            }
            
        # Actual distribution
        distribution_result = distribution_utils.distribute_reward(
            user=user,
            reward_config=config,
            amount=amount,
            metadata={
                **metadata,
                'trigger_event': trigger_event,
                'calculated_by': 'reward_service'
            }
        )
        
        if not distribution_result['success']:
            return distribution_result
            
        return {
            'success': True,
            'reward': distribution_result['user_reward'],
            'transaction': distribution_result['transaction'],
            'message': f'Successfully granted {amount} {reward_type} reward'
        }

    def get_user_rewards_summary(self, user: Any) -> Dict[str, Any]:
        """
        Gets comprehensive summary of user's rewards.
        
        Utils used:
        - analytics_utils.get_user_reward_summary (core summary)
        - configuration_utils.get_active_reward_configs (for available rewards)
        """
        summary = analytics_utils.get_user_reward_summary(user.id)
        available_rewards = configuration_utils.get_active_reward_configs()
        
        return {
            'success': True,
            'summary': summary,
            'available_rewards': [
                cfg for cfg in available_rewards 
                if validation_utils.validate_reward_eligibility(user, cfg['reward_type'], cfg)['eligible']
            ]
        }

    def redeem_reward(
        self,
        user: Any,
        reward_type: str,
        redemption_amount: Decimal,
        redemption_type: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Redeems a reward for specific benefits.
        
        Utils used:
        - validation_utils.validate_reward_amount (amount validation)
        - distribution_utils.redeem_reward (core redemption)
        - configuration_utils.get_reward_config (config lookup)
        """
        config = configuration_utils.get_reward_config(reward_type, user.tier)
        if not config:
            return {
                'success': False,
                'error': 'NO_ACTIVE_CONFIG',
                'message': f'No active configuration for {reward_type} rewards'
            }
            
        # Amount validation
        amount_check = validation_utils.validate_reward_amount(redemption_amount, config, user.tier)
        if not amount_check['valid']:
            return {
                'success': False,
                **amount_check
            }
            
        # Handle redemption
        redemption_result = distribution_utils.redeem_reward(
            user=user,
            reward_config=config,
            redemption_amount=redemption_amount,
            redemption_type=redemption_type,
            metadata=metadata
        )
        
        if not redemption_result['success']:
            return redemption_result
            
        return {
            'success': True,
            'amount_redeemed': redemption_amount,
            'redemption_type': redemption_type,
            'remaining_balance': redemption_result['remaining_balance'],
            'transaction': redemption_result['transaction']
        }