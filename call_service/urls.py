from django.urls import path
from .views import (
    StartCallAPIView,
    EndCallAPIView,
    MyCallHistoryAPIView,
    AdminCallListAPIView,
    AdminEndCallAPIView,
)

urlpatterns = [
    # User APIs
    path("start-call/", StartCallAPIView.as_view(), name="start-call"),
    path("end-call/<uuid:call_id>/", EndCallAPIView.as_view(), name="end-call"),
    path("my-call-history/", MyCallHistoryAPIView.as_view(), name="my-call-history"),

    # Admin APIs
    path("admin/calls/", AdminCallListAPIView.as_view(), name="admin-call-list"),
    path("admin/end-call/<uuid:call_id>/", AdminEndCallAPIView.as_view(), name="admin-end-call"),
]
