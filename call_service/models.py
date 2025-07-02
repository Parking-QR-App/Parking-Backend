from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.postgres.fields import JSONField  # or use models.JSONField for Django 3.1+
import uuid

User = settings.AUTH_USER_MODEL

class CallRecord(models.Model):
    call_id = models.CharField(max_length=100, unique=True)

    inviter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,   # allow null for now
        blank=True
    )
    invitee = models.ForeignKey(
        User,
        related_name='invitee_calls',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    call_type = models.CharField(max_length=20, default='audio')  # or 'video', etc.
    custom_data = models.JSONField(default=dict, blank=True)  # requires Django 3.1+, else use JSONField from postgres

    state = models.CharField(
        max_length=20,
        choices=[
            ('initiated', 'Initiated'),
            ('incoming', 'Incoming'),  # new
            ('accepted', 'Accepted'),
            ('rejected', 'Rejected'),
            ('busy', 'Busy'),          # new
            ('canceled', 'Canceled'),
            ('missed', 'Missed'),
            ('ended', 'Ended'),        # new
        ],
        default='initiated'
    )

    duration = models.IntegerField(null=True, blank=True, help_text="Duration in seconds")

    # reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # Optional: for better analytics
    ended_at = models.DateTimeField(null=True, blank=True)
    was_connected = models.BooleanField(default=False)

    def __str__(self):
        return f"Call {self.call_id} from {self.inviter_id} to {self.invitee_id} [{self.state}]"
