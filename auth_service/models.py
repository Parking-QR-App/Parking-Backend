from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import now
from django.contrib.postgres.fields import CIEmailField  # Case-insensitive email
from django.db.models import Index
import uuid;

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
        return f"{self.phone_number}"


class BlacklistedAccessToken(models.Model):
    token = models.CharField(max_length=500, unique=True)
    created_at = models.DateTimeField(default=now)

    class Meta:
        indexes = [
            Index(fields=['token']),
        ]

    def __str__(self):
        return f"Blacklisted Token: {self.token}"


class UserDevice(models.Model):
    DEVICE_TYPES = [
        ("android", "Android"),
        ("ios", "iOS"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices")
    fcm_token = models.CharField(max_length=255, unique=True)
    device_type = models.CharField(max_length=10, choices=DEVICE_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            Index(fields=['fcm_token']),
        ]

    def __str__(self):
        return f"Device for User {self.user.phone_number} - {self.device_type}"
