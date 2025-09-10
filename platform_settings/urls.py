from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()

urlpatterns = [
    # Platform Settings
    path('settings/', views.PlatformSettingListView.as_view(), name='settings-list'),
    path('settings/<str:key>/', views.PlatformSettingDetailView.as_view(), name='setting-detail'),
    path('settings/<str:key>/update/', views.UpdatePlatformSettingView.as_view(), name='setting-update'),
    
    # User Balances
    path('balances/', views.UserCallBalanceListView.as_view(), name='balances-list'),
    path('balances/bulk-update/', views.BulkBalanceUpdateView.as_view(), name='bulk-balance-update'),
    path('balances/<str:user_id>/', views.UserCallBalanceDetailView.as_view(), name='balance-detail'),

    # Reset Logs
    path('reset-logs/', views.BalanceResetLogListView.as_view(), name='reset-logs'),
    
    # Operations
    path('execute-cron-reset/', views.ExecuteCronResetView.as_view(), name='execute-cron-reset'),
    path('initialize-settings/', views.InitializeSettingsView.as_view(), name='initialize-settings'),
]

urlpatterns += router.urls