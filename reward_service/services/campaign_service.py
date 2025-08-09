from typing import Dict, Optional, Any, List
from django.utils import timezone
from decimal import Decimal

from ..models import RewardConfiguration
from ..utils import (
    configuration_utils,
    analytics_utils,
    calculation_utils,
    validation_utils
)

class CampaignRewardService:
    """
    Handles campaign-specific reward operations and analytics.
    Systematically uses all relevant utils with campaign context.
    """
    
    def get_campaign_rewards(
        self,
        campaign_id: str,
        user_tier: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Gets all reward configurations for a campaign.
        
        Utils used:
        - configuration_utils.get_active_reward_configs
        - configuration_utils.get_reward_config (per type)
        """
        configs = configuration_utils.get_active_reward_configs(
            include_campaign_configs=True
        )
        
        return [
            cfg for cfg in configs
            if str(cfg.get('campaign_id')) == campaign_id
        ]

    def calculate_campaign_performance(
        self,
        campaign_id: str,
        period: str = '30d'
    ) -> Dict[str, Any]:
        """
        Calculates comprehensive performance metrics for a campaign.
        
        Utils used:
        - analytics_utils.calculate_reward_roi
        - analytics_utils.calculate_reward_metrics
        - configuration_utils.calculate_config_effectiveness (per config)
        """
        roi = analytics_utils.calculate_reward_roi(
            campaign_id=campaign_id,
            period=period
        )
        
        metrics = analytics_utils.calculate_reward_metrics(
            reward_type=None,
            period=period
        )
        
        configs = self.get_campaign_rewards(campaign_id)
        config_effectiveness = [
            configuration_utils.calculate_config_effectiveness(str(cfg['id']))
            for cfg in configs
        ]
        
        return {
            'roi': roi,
            'overall_metrics': metrics,
            'config_effectiveness': config_effectiveness
        }

    def create_campaign_reward(
        self,
        campaign_id: str,
        reward_type: str,
        base_amount: Decimal,
        modifiers: Optional[Dict[str, Any]] = None,
        created_by: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Creates a new campaign-specific reward configuration.
        
        Utils used:
        - calculation_utils.calculate_reward_amount (for base calculation)
        - configuration_utils.create_reward_config
        """
        if not modifiers:
            modifiers = {}
            
        # Calculate base reward amount
        base_result = calculation_utils.calculate_reward_amount(
            reward_type=reward_type,
            base_amount=base_amount,
            user_tier='basic',  # Base tier
            metadata=modifiers
        )
        
        # Create config
        config_data = {
            'name': f"Campaign {campaign_id} - {reward_type}",
            'reward_type': reward_type,
            'value_per_unit': base_result['amount'],
            'campaign_id': campaign_id,
            **modifiers
        }
        
        if created_by:
            config_data['created_by'] = created_by
            
        return configuration_utils.create_reward_config(config_data)