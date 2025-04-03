from channels.generic.websocket import WebsocketConsumer
import json
from django.utils.timezone import now
from .models import Call

class CallConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()
        self.user = self.scope["user"]

    def disconnect(self, close_code):
        # Auto-end the call when a user disconnects
        call = Call.objects.filter(
            host=self.user, call_status="ongoing"
        ).first() or Call.objects.filter(
            guest=self.user, call_status="ongoing"
        ).first()

        if call:
            call.end_call(status="ended")
