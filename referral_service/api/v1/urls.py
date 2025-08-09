from django.urls import path
from .views import (
    UserReferralCodeView,
    CreateCampaignCodeView,
    ReferralCodeDetailView,
    ApplyReferralCodeView,
    ReferralRelationshipDetailView,
    UserReferralListView,
    ReferralLimitDetailView,
    AdminSetLimitsView,
    AdminAdjustLimitsView,
    ReferralCodeBatchCreateView,
    RegisterWithReferralView,
    DeactivateReferralCodeView
)

app_name = 'referral_service'

urlpatterns = [
    # User referral code generation / retrieval
    path('code/user/', UserReferralCodeView.as_view(), name='user-referral-code-create'),

    path('code/deactivate/', DeactivateReferralCodeView.as_view(), name='deactivate-referral-code'),

    # Campaign code creation (admin)
    path('code/campaign/create/', CreateCampaignCodeView.as_view(), name='create-campaign-code'),

    # Referral code detail
    path('code/<str:code_id>/', ReferralCodeDetailView.as_view(), name='referral-code-detail'),

    # Apply referral during registration
    path('relationship/apply/', ApplyReferralCodeView.as_view(), name='apply-referral-code'),

    # Relationship detail
    path('relationship/<str:relationship_id>/', ReferralRelationshipDetailView.as_view(), name='relationship-detail'),

    # List referrals for current user
    path('relationship/me/', UserReferralListView.as_view(), name='user-referral-list'),

    # Referral limit view
    path('limit/<str:user_id>/', ReferralLimitDetailView.as_view(), name='referral-limit-detail'),

    # Admin limit management
    path('admin/limit/set/', AdminSetLimitsView.as_view(), name='admin-set-limits'),
    path('admin/limit/adjust/', AdminAdjustLimitsView.as_view(), name='admin-adjust-limits'),

    # Batch creation and inspection
    path('code/batch/create/', ReferralCodeBatchCreateView.as_view(), name='batch-create'),
    path('register-with-referral/', RegisterWithReferralView.as_view(), name='register-with-referral'),
]
