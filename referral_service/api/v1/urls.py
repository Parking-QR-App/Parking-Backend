from django.urls import path
from . import views

app_name = 'referral_service'

urlpatterns = [
    # User referral code generation / retrieval
    path('code/user/', views.UserReferralCodeView.as_view(), name='user-referral-code-create'),
    
    # Deactivate referral code by Admin
    path('code/deactivate/', views.DeactivateReferralCodeView.as_view(), name='deactivate-referral-code'),
    
    # Campaign code creation (admin)
    path('code/campaign/create/', views.CreateCampaignCodeView.as_view(), name='create-campaign-code'),
    
    # Referral code detail Admin
    path(
        "code/<str:id>/",
        views.ReferralCodeDetailView.as_view(),
        name="referral-code-detail",
    ),
    
    # Relationship detail Admin
    path('relationship/<str:relationship_id>/', views.ReferralRelationshipDetailView.as_view(), name='relationship-detail'),
    
    # List referrals for current user
    path('relationship/me/', views.UserReferralListView.as_view(), name='user-referral-list'),
    
    # Register with referral code
    path('register-with-referral/', views.RegisterWithReferralView.as_view(), name='register-with-referral'),
    
    # Admin settings
    path('admin/settings/', views.ReferralSettingsView.as_view(), name='referral-settings'),
    path('admin/campaigns/', views.CampaignCodeListView.as_view(), name='campaign-list'),
]