from django.urls import path
from .views import NotificationAPI, NotificationDetailAPI, NotificationListAPI, MarkAllAsReadAPI, UnreadCountAPI

urlpatterns = [
    path('notifications/', NotificationAPI.as_view(), name='send-notification'),
    path('notifications/<int:notification_id>/', NotificationDetailAPI.as_view(), name='notification-detail'),
    path('notifications/lists/', NotificationListAPI.as_view(), name='notification-list'),
    path('notifications/mark-all-read/', MarkAllAsReadAPI.as_view(), name='mark-all-read'),
    path('notifications/unread-count/', UnreadCountAPI.as_view(), name='unread-count')
]