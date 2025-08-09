from typing import Dict, Optional, Any, List
from django.utils import timezone

from ..models import RewardConfiguration
from ..utils import (
    configuration_utils,
    analytics_utils,
    validation_utils
)

class RewardConfigurationService:
    """
    Handles all reward configuration operations including creation, updates, and analytics.
    Systematically uses all configuration and analytics utils.
    """
    
    def get_active_configurations(
        self,
        reward_types: Optional[List[str]] = None,
        include_campaign_configs: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Retrieves active reward configurations with optional filtering.
        
        Utils used:
        - configuration_utils.get_active_reward_configs
        """
        return configuration_utils.get_active_reward_configs(
            reward_types=reward_types,
            include_campaign_configs=include_campaign_configs
        )

    def get_configuration(
        self,
        reward_type: str,
        user_tier: Optional[str] = None,
        campaign_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Gets a specific reward configuration with tier modifications applied.
        
        Utils used:
        - configuration_utils.get_reward_config
        """
        return configuration_utils.get_reward_config(
            reward_type=reward_type,
            user_tier=user_tier,
            campaign_id=campaign_id
        )

    def create_configuration(
        self,
        config_data: Dict[str, Any],
        created_by: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Creates a new reward configuration with validation.
        
        Utils used:
        - configuration_utils.create_reward_config
        - validation_utils._validate_new_config_data
        """
        validation = validation_utils._validate_new_config_data(config_data)
        if not validation['valid']:
            return {
                'success': False,
                **validation
            }
            
        if created_by:
            config_data['created_by'] = created_by
            
        return configuration_utils.create_reward_config(config_data)

    def update_configuration(
        self,
        config_id: str,
        updates: Dict[str, Any],
        updated_by: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Updates an existing reward configuration with validation.
        
        Utils used:
        - configuration_utils.update_reward_config
        - validation_utils._validate_config_updates
        """
        if updated_by:
            updates['updated_by'] = updated_by
            
        return configuration_utils.update_reward_config(config_id, updates)

    def clone_configuration(
        self,
        source_config_id: str,
        new_name: str,
        modifications: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Clones a reward configuration with optional modifications.
        
        Utils used:
        - configuration_utils.clone_reward_config
        """
        return configuration_utils.clone_reward_config(
            source_config_id=source_config_id,
            new_name=new_name,
            modifications=modifications
        )

    def calculate_configuration_effectiveness(
        self,
        config_id: str
    ) -> Dict[str, Any]:
        """
        Calculates effectiveness metrics for a reward configuration.
        
        Utils used:
        - configuration_utils.calculate_config_effectiveness
        - analytics_utils.calculate_reward_roi (if campaign exists)
        """
        effectiveness = configuration_utils.calculate_config_effectiveness(config_id)
        
        if not effectiveness.get('error'):
            config = RewardConfiguration.objects.get(id=config_id)
            if config.campaign:
                effectiveness['roi'] = analytics_utils.calculate_reward_roi(
                    campaign_id=str(config.campaign.id)
                )
                
        return effectiveness