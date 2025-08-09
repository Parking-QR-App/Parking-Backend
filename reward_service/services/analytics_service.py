from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
from django.utils import timezone

from ..utils import (
    analytics_utils,
    configuration_utils,
    calculation_utils
)

class RewardAnalyticsService:
    """
    Handles all reward analytics operations, systematically using all analytics utils.
    Provides comprehensive reward performance insights.
    """
    
    def get_reward_metrics(
        self,
        user_id: Optional[str] = None,
        reward_type: Optional[str] = None,
        period: str = '30d'
    ) -> Dict[str, Any]:
        """
        Gets comprehensive reward metrics for a given scope.
        
        Utils used:
        - analytics_utils.calculate_reward_metrics
        """
        return analytics_utils.calculate_reward_metrics(
            user_id=user_id,
            reward_type=reward_type,
            period=period
        )

    def get_reward_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        group_by: str = 'day'
    ) -> Dict[str, Any]:
        """
        Gets time-based reward analytics with grouping.
        
        Utils used:
        - analytics_utils.get_reward_analytics
        """
        return analytics_utils.get_reward_analytics(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )

    def get_reward_trends(
        self,
        period_days: int = 30,
        comparison_period_days: int = 30
    ) -> Dict[str, Any]:
        """
        Gets reward trends comparing two periods.
        
        Utils used:
        - analytics_utils.generate_reward_trends
        """
        return analytics_utils.generate_reward_trends(
            period_days=period_days,
            comparison_period_days=comparison_period_days
        )

    def calculate_reward_roi(
        self,
        campaign_id: Optional[str] = None,
        period: str = '30d'
    ) -> Dict[str, Any]:
        """
        Calculates ROI for rewards associated with a campaign.
        
        Utils used:
        - analytics_utils.calculate_reward_roi
        """
        return analytics_utils.calculate_reward_roi(
            campaign_id=campaign_id,
            period=period
        )

    def get_user_reward_summary(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Gets comprehensive reward summary for a user.
        
        Utils used:
        - analytics_utils.get_user_reward_summary
        - configuration_utils.get_active_reward_configs
        """
        return analytics_utils.get_user_reward_summary(user_id)