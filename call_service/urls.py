from django.urls import path
from .views import (
    CallEventAPIView,
    ZegoTokenView
)

urlpatterns = [
    path("event/", CallEventAPIView.as_view(), name="call_event"),
    path("calltoken/", ZegoTokenView.as_view(), name="zego-token"),
]
