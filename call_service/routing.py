from django.urls import re_path
from .consumers import CallConsumer

websocket_urlpatterns = [
    re_path(r"ws/call/$", CallConsumer.as_asgi()),
]
