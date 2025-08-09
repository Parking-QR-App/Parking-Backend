from django.db import models
from django.conf import settings

class Notification(models.Model):
    class Type(models.TextChoices):
        PARKING_ALERT = "parking_alert", "Parking Alert"
        MESSAGE = "message", "New Message"
        OTP = "otp", "OTP Code"

    sender = models.ForeignKey(  # New field
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_notifications',
        null=True,  # For system-generated notifications
        blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_notifications'  # Updated related_name
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    title = models.CharField(max_length=100)
    message = models.TextField()
    metadata = models.JSONField(default=dict)
    is_read = models.BooleanField(default=False)
    is_delivered = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)  # Added this field

    class Meta:
        indexes = [
            # Existing indexes
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['created_at']),
            
            # New indexes for sender-related queries
            models.Index(fields=['sender', 'created_at']),
            models.Index(fields=['sender', 'user', 'created_at']),
            
            # For admin reporting
            models.Index(fields=['type', 'created_at']),
        ]
        ordering = ['-created_at']  # New default ordering
        get_latest_by = 'created_at'

    def mark_as_read(self):
        """Mark notification as read and update timestamps"""
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read', 'modified_at'])
            return True
        return False