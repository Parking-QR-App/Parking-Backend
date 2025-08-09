from django.db import transaction
from decimal import Decimal
from typing import Dict, Optional, Any

from ..models import RewardConfiguration
from ..utils import (
    calculation_utils,
    validation_utils,
    distribution_utils,
    configuration_utils
)

class ReferralRewardService:
    """
    Handles referral-specific reward operations with strict validation.
    Systematically uses all relevant utils with referral context.
    """
    
    def calculate_referral_reward(
        self,
        referrer: Any,
        referred_user: Any,
        referral_count: int,
        base_amount: Decimal
    ) -> Dict[str, Any]:
        """
        Calculates referral reward with all applicable bonuses.
        
        Utils used:
        - calculation_utils.calculate_progressive_bonus
        - calculation_utils.calculate_reward_amount
        - calculation_utils.apply_seasonal_multiplier
        - validation_utils.validate_reward_amount
        """
        # Get referral config
        config = configuration_utils.get_reward_config('referral', referrer.tier)
        if not config:
            return {
                'success': False,
                'error': 'NO_REFERRAL_CONFIG',
                'message': 'No active referral reward configuration'
            }
            
        # Calculate progressive bonus
        progressive_result = calculation_utils.calculate_progressive_bonus(
            referral_count=referral_count,
            base_reward=base_amount
        )
        
        # Calculate base reward with tier multipliers
        reward_result = calculation_utils.calculate_reward_amount(
            reward_type='referral',
            base_amount=progressive_result['final_amount'],
            user_tier=referrer.tier,
            metadata={
                'referral_count': referral_count,
                'milestone_reached': progressive_result['milestone_reached']
            }
        )
        
        # Apply seasonal multiplier if applicable
        seasonal_result = calculation_utils.apply_seasonal_multiplier(reward_result['amount'])
        if seasonal_result['is_promotional_period']:
            reward_result['amount'] = seasonal_result['final_amount']
            reward_result['calculation_breakdown']['seasonal_multiplier'] = seasonal_result['seasonal_multiplier']
            
        # Validate final amount
        amount_check = validation_utils.validate_reward_amount(
            reward_result['amount'],
            config,
            referrer.tier
        )
        
        if not amount_check['valid']:
            return {
                'success': False,
                **amount_check
            }
            
        return {
            'success': True,
            'calculated_reward': reward_result,
            'progressive_bonus': progressive_result,
            'config': config
        }

    @transaction.atomic
    def grant_referral_rewards(
        self,
        referrer: Any,
        referred_user: Any,
        referral_relationship_id: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Grants rewards for both referrer and referred user after validation.
        
        Utils used:
        - validation_utils.validate_reward_eligibility (both users)
        - distribution_utils.distribute_reward (both rewards)
        - configuration_utils.get_reward_config (both rewards)
        """
        if not metadata:
            metadata = {}
            
        metadata['referral_relationship_id'] = referral_relationship_id
        
        # Get configs
        referrer_config = configuration_utils.get_reward_config('referral', referrer.tier)
        referred_config = configuration_utils.get_reward_config('registration', referred_user.tier)
        
        if not referrer_config or not referred_config:
            return {
                'success': False,
                'error': 'MISSING_CONFIG',
                'message': 'Missing reward configuration for referral or registration'
            }
            
        # Calculate referrer reward
        referral_count = metadata.get('referral_count', 0)
        reward_calc = self.calculate_referral_reward(
            referrer=referrer,
            referred_user=referred_user,
            referral_count=referral_count,
            base_amount=referrer_config['value_per_unit']
        )
        
        if not reward_calc['success']:
            return reward_calc
            
        referrer_amount = reward_calc['calculated_reward']['amount']
        
        # Validate referrer eligibility
        referrer_eligibility = validation_utils.validate_reward_eligibility(
            referrer,
            'referral',
            referrer_config,
            metadata
        )
        
        if not referrer_eligibility['eligible']:
            return {
                'success': False,
                **referrer_eligibility
            }
            
        # Validate referred user eligibility
        referred_eligibility = validation_utils.validate_reward_eligibility(
            referred_user,
            'registration',
            referred_config,
            metadata
        )
        
        if not referred_eligibility['eligible']:
            return {
                'success': False,
                **referred_eligibility
            }
            
        # Distribute both rewards
        referrer_result = distribution_utils.distribute_reward(
            user=referrer,
            reward_config=referrer_config,
            amount=referrer_amount,
            metadata={
                **metadata,
                'trigger_event': 'referral_verified',
                'referred_user_id': str(referred_user.id)
            }
        )
        
        referred_result = distribution_utils.distribute_reward(
            user=referred_user,
            reward_config=referred_config,
            amount=referred_config['value_per_unit'],
            metadata={
                **metadata,
                'trigger_event': 'registration_completed',
                'referrer_user_id': str(referrer.id)
            }
        )
        
        if not referrer_result['success'] or not referred_result['success']:
            return {
                'success': False,
                'referrer_error': referrer_result.get('error'),
                'referred_error': referred_result.get('error'),
                'message': 'Failed to distribute one or both rewards'
            }
            
        return {
            'success': True,
            'referrer_reward': referrer_result,
            'referred_reward': referred_result,
            'message': 'Successfully distributed referral rewards'
        }