from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import now
from django.db.models import Index
import uuid;
from django.conf import settings

def default_device_id():
    from django.utils.crypto import get_random_string
    return f"dev_{get_random_string(12)}"

def default_token_expiry():
    from django.utils import timezone
    return timezone.now() + timezone.timedelta(days=30)

class UserManager(BaseUserManager):
    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError("The Phone number must be set")

        extra_fields.setdefault('is_active', True)

        # Lowercase email if provided
        if 'email' in extra_fields and extra_fields['email']:
            extra_fields['email'] = extra_fields['email'].lower()

        user = self.model(phone_number=phone_number, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user


    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if not extra_fields.get('is_staff'):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get('is_superuser'):
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(phone_number, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(max_length=15, unique=True)

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)

    email = models.EmailField(
    unique=True,
    null=True,
    blank=True,
    )

    first_name = models.CharField(max_length=30, null=True, blank=True)
    last_name = models.CharField(max_length=30, null=True, blank=True)

    user_id = models.CharField(max_length=128, unique=True, editable=False, null=False)
    user_name = models.CharField(max_length=50, unique=True, blank=True, null=True)

    email_verified = models.BooleanField(default=False)

    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_expiry = models.DateTimeField(null=True, blank=True)

    email_otp = models.CharField(max_length=6, null=True, blank=True)
    email_otp_expiry = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = []

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_user_set',
        blank=True
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_user_permissions_set',
        blank=True
    )

    class Meta:
        indexes = [
            Index(fields=['phone_number']),
            Index(fields=['email']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['phone_number'], name='unique_user_phone'),
            models.UniqueConstraint(fields=['email'], name='unique_user_email'),
        ]

    def __str__(self):
        return f"{self.id}".strip()  # Return the id as a string identifier for display
    
    def get_short_name(self):
        """Return the short name for the user."""
        if self.first_name:
            return self.first_name
        elif hasattr(self, 'user_name') and self.user_name:
            return self.user_name
        elif self.username:
            return self.username
        return ''
    
    def get_full_name(self):
        """Return the full name for the user."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.get_short_name()


class UserDevice(models.Model):
    DEVICE_TYPES = [
        ('android', 'Android'),
        ('ios', 'iOS'),
        ('web', 'Web')
    ]
    
    # Required Fields
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='devices'
    )
    fcm_token = models.CharField(max_length=255, unique=True)
    device_type = models.CharField(max_length=10, choices=DEVICE_TYPES)
    
    # New Fields with Safe Defaults
    device_id = models.CharField(
        max_length=255,
        unique=True,
        default=default_device_id
    )
    os_version = models.CharField(
        max_length=50,
        default='',
        blank=True
    )
    ip_address = models.GenericIPAddressField(
        default='0.0.0.0',
        blank=True,
        null=True
    )
    last_active = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_access_token = models.TextField(blank=True, null=True)
    last_refresh_token_jti = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = [('user', 'device_id')]  # One device_id per user

    def __str__(self):
        return f"{self.user.user_name}'s {self.device_type} device"

class BlacklistedAccessToken(models.Model):
    token = models.CharField(max_length=255, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='blacklisted_tokens'
    )
    expires_at = models.DateTimeField(
        default=default_token_expiry  
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            Index(fields=['token']),
        ]

    def __str__(self):
        return f"Blacklisted token for {self.user.user_name}"