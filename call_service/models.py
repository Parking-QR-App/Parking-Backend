from django.conf import settings
from django.db import models
from django.utils import timezone
import uuid

class Call(models.Model):
    STATUS_CHOICES = [
        ("ongoing", "Ongoing"),
        ("ended", "Ended"),
        ("missed", "Missed"),
        ("failed", "Failed"),
    ]

    guest = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="guest_calls"  # 👈 Add a unique related_name
    )
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="host_calls"  # 👈 Add a unique related_name
    )
    def generate_room_name():
        return f"call-{uuid.uuid4().hex[:8]}"
    
    room_name = models.CharField(max_length=255, unique=True, default=generate_room_name)
    
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)

    call_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="ongoing")

    recording_url = models.URLField(null=True, blank=True)  # Store Jitsi recording link if enabled
    error_message = models.TextField(null=True, blank=True)  # Store failure reasons (e.g., network issues)

    # subscription_plan = models.ForeignKey("subscription_service.UserSubscription", null=True, blank=True, on_delete=models.SET_NULL)

    def end_call(self, status="ended"):
        self.end_time = timezone.now()
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()
        self.call_status = status
        self.save()
