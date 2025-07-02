from django.db import models
from django.utils import timezone
from django.conf import settings
import uuid

class QRCode(models.Model):
    qr_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="qr_codes", 
        null=True, 
        blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.qr_id)


class QRCodeAnalytics(models.Model):
    qr_code = models.OneToOneField(
        QRCode, 
        on_delete=models.CASCADE, 
        related_name="analytics"
    )
    scan_count = models.IntegerField(default=0)
    unique_users = models.IntegerField(default=0)
    last_scanned = models.DateTimeField(null=True, blank=True)
    unique_user_list = models.JSONField(default=list)

    def increment_scan_count(self, user):
        self.scan_count += 1
        if user and user.id not in self.unique_user_list:
            self.unique_users += 1
            self.unique_user_list.append(str(user.id))
        self.last_scanned = timezone.now()
        self.save()
