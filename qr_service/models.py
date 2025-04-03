from django.db import models
from django.utils import timezone
from django.conf import settings
import uuid

class QRCode(models.Model):
    qr_id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="qr_codes", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

class QRCodeAnalytics(models.Model):
    qr_code = models.OneToOneField(QRCode, on_delete=models.CASCADE, related_name="analytics")
    scan_count = models.IntegerField(default=0)
    unique_users = models.IntegerField(default=0)
    last_scanned = models.DateTimeField(null=True, blank=True)
    unique_user_list = models.JSONField(default=list)  # Track unique users who scanned the QR

    def increment_scan_count(self, user):
        """Update analytics when a QR code is scanned."""
        self.scan_count += 1
        if user and user.id not in self.unique_user_list:
            self.unique_users += 1
            self.unique_user_list.append(user.id)  # Track unique users
        self.last_scanned = timezone.now()
        self.save()
