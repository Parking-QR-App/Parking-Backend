from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid
from django.db.models import Index
from decimal import Decimal

User = settings.AUTH_USER_MODEL

class CallRecord(models.Model):
    CALL_TYPES = [
        ('audio', 'Audio Call'),
        ('video', 'Video Call'),
    ]

    CALL_STATES = [
        ('initiated', 'Initiated'),
        ('ringing', 'Ringing'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('busy', 'Busy'),
        ('canceled', 'Canceled'),
        ('missed', 'Missed'),
        ('ended', 'Ended'),
        ('failed', 'Failed'),
    ]

    call_id = models.CharField(max_length=100, unique=True, db_index=True)

    # Participants
    inviter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='outgoing_calls'
    )
    invitee = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='incoming_calls'
    )

    # Call details
    call_type = models.CharField(max_length=20, choices=CALL_TYPES, default='audio')
    custom_data = models.JSONField(default=dict, blank=True)

    # State management
    state = models.CharField(max_length=20, choices=CALL_STATES, default='initiated')
    previous_state = models.CharField(max_length=20, blank=True, null=True)

    # Timing analytics
    initiated_at = models.DateTimeField(default=timezone.now)
    ringing_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration = models.IntegerField(default=0, help_text="Duration in seconds")

    # Response time metrics
    ring_duration = models.IntegerField(default=0, null=True, blank=True, help_text="Time from ring to answer/reject (ms)")
    response_time = models.IntegerField(default=0, null=True, blank=True, help_text="Time from initiation to answer/reject (ms)")

    # Network & security
    inviter_ip = models.GenericIPAddressField(null=True, blank=True)
    invitee_ip = models.GenericIPAddressField(null=True, blank=True)
    inviter_device = models.CharField(max_length=200, blank=True)
    invitee_device = models.CharField(max_length=200, blank=True)

    # Quality metrics
    was_connected = models.BooleanField(default=False)
    call_quality_rating = models.FloatField(null=True, blank=True, help_text="Average rating from participants")
    inviter_rating = models.FloatField(null=True, blank=True)
    invitee_rating = models.FloatField(null=True, blank=True)
    inviter_feedback = models.TextField(blank=True)
    invitee_feedback = models.TextField(blank=True)

    # Cost tracking - REMOVE cost_deducted field since we'll handle this transactionally
    call_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    deducted_from_bonus = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    deducted_from_base = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    deduction_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('not_applicable', 'Not Applicable')  # for missed/rejected calls
        ],
        default='pending'
    )

    # System fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            Index(fields=['call_id']),
            Index(fields=['inviter', 'initiated_at']),
            Index(fields=['invitee', 'initiated_at']),
            Index(fields=['state']),
            Index(fields=['initiated_at']),
            Index(fields=['deduction_status']),
        ]

    def __str__(self):
        return f"Call {self.call_id}: {self.inviter} → {self.invitee} [{self.state}]"

    def save(self, *args, **kwargs):
        # Ensure duration is always integer
        if self.ended_at and self.accepted_at:
            self.duration = int((self.ended_at - self.accepted_at).total_seconds())

        if self.ringing_at and self.initiated_at:
            self.ring_duration = int((self.ringing_at - self.initiated_at).total_seconds())

        if self.accepted_at and self.initiated_at:
            self.response_time = int((self.accepted_at - self.initiated_at).total_seconds())

        super().save(*args, **kwargs)

    @property
    def total_duration(self):
        """Calculate total call duration in seconds"""
        if self.accepted_at and self.ended_at:
            return (self.ended_at - self.accepted_at).total_seconds()
        return 0

    @property
    def answer_time(self):
        """Time taken to answer the call"""
        if self.ringing_at and self.accepted_at:
            return (self.accepted_at - self.ringing_at).total_seconds()
        return None

    @property
    def should_charge(self):
        """Determine if this call should incur charges"""
        return self.state == 'ended' and self.was_connected and self.duration > 0

class CallEventLog(models.Model):
    """
    Detailed log of all call events for analytics
    """
    call = models.ForeignKey(CallRecord, on_delete=models.CASCADE, related_name='event_logs')
    event_type = models.CharField(max_length=50)
    event_data = models.JSONField(default=dict)
    timestamp = models.DateTimeField(default=timezone.now)
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            Index(fields=['call', 'timestamp']),
            Index(fields=['event_type']),
        ]

    def __str__(self):
        return f"{self.call.call_id} - {self.event_type} at {self.timestamp}"