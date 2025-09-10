from django.urls import path
from .views import (
    CallEventAPIView, CallRatingAPIView, 
    CallAnalyticsAPIView, CallHistoryAPIView,
    CallDetailAPIView, AdminCallAnalyticsAPIView,
    ZegoTokenView
)

urlpatterns = [
    path("event/", CallEventAPIView.as_view(), name="call_event"),
    path("rating/", CallRatingAPIView.as_view(), name="call_rating"),
    path("analytics/", CallAnalyticsAPIView.as_view(), name="call_analytics"),
    path("history/", CallHistoryAPIView.as_view(), name="call_history"),
    path("detail/<str:call_id>/", CallDetailAPIView.as_view(), name="call_detail"),
    path("admin/analytics/", AdminCallAnalyticsAPIView.as_view(), name="admin_call_analytics"),
    path("calltoken/", ZegoTokenView.as_view(), name="zego-token"),
]