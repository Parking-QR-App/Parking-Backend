from .code_views import (
    UserReferralCodeView,
    CreateCampaignCodeView,
    ReferralCodeDetailView,
    DeactivateReferralCodeView
)
from .relationship_views import (
    ApplyReferralCodeView,
    ReferralRelationshipDetailView,
    UserReferralListView,
)
from .limit_views import (
    ReferralLimitDetailView,
)
from .admin_views import (
    AdminSetLimitsView,
    AdminAdjustLimitsView,
)
from .batch_views import (
    ReferralCodeBatchCreateView
)

from .registration_with_referral import RegisterWithReferralView

__all__ = [
    'UserReferralCodeView',
    'CreateCampaignCodeView',
    'ReferralCodeDetailView',
    'ApplyReferralCodeView',
    'ReferralRelationshipDetailView',
    'UserReferralListView',
    'ReferralLimitDetailView',
    'AdminSetLimitsView',
    'AdminAdjustLimitsView',
    'ReferralCodeBatchCreateView',
    'RegisterWithReferralView',
    'DeactivateReferralCodeView'
]
