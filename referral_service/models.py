from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
import uuid
import string
import random
from decimal import Decimal
from django.apps import apps
import logging
logger = logging.getLogger(__name__)

def generate_referral_code():
    ReferralSettings = apps.get_model('referral_service', 'ReferralSettings')
    setting = ReferralSettings.objects.filter(key='referral_code_length', is_active=True).first()
    length = int(setting.value) if setting and setting.value.isdigit() else 8

    ReferralCode = apps.get_model('referral_service', 'ReferralCode')

    for _ in range(5):  # Try 5 times to avoid collision
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
        if not ReferralCode.objects.filter(code=code).exists():
            return code

    logger.warning("Could not find unique referral code after 5 attempts")
    return code  # Return last attempt anyway

class ReferralCode(models.Model):
    """
    Stores referral codes - both user-generated and admin campaign codes
    """
    CODE_TYPES = [
        ('user', 'User Generated'),
        ('campaign', 'Campaign Code'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, default=generate_referral_code)
    
    # Owner (null for campaign codes)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_codes',
        null=True,
        blank=True
    )
    
    # Code metadata
    code_type = models.CharField(max_length=10, choices=CODE_TYPES, default='user')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    # Usage tracking
    usage_count = models.PositiveIntegerField(default=0)
    max_usage = models.PositiveIntegerField(default=0)  # 0 = unlimited
    
    # Time constraints
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    
    # Reward configuration (for campaign codes)
    reward_calls = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['owner']),
            models.Index(fields=['code_type']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.code} ({self.get_code_type_display()})"

    @property
    def is_valid(self):
        """Check if code is currently valid for use"""
        now = timezone.now()
        is_active = self.status == 'active'
        is_within_dates = self.valid_from <= now and (self.valid_until is None or self.valid_until >= now)
        has_usage_left = self.max_usage == 0 or self.usage_count < self.max_usage
        
        return is_active and is_within_dates and has_usage_left

class ReferralRelationship(models.Model):
    """
    Tracks who referred whom
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # The referral relationship
    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referrals_made',
        null=True,         
        blank=True
    )
    referred_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_received'
    )
    referral_code = models.ForeignKey(
        ReferralCode,
        on_delete=models.CASCADE,
        related_name='relationships'
    )
    
    # Status tracking
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    
    # Reward tracking
    reward_calls_given = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00')
    )
    reward_given_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['referred_user'], name='unique_referral_per_user'),
        ]

    def __str__(self):
        return f"{self.referrer} → {self.referred_user}"

class ReferralSettings(models.Model):
    """
    Admin-controlled referral settings
    """
    key = models.CharField(max_length=100, unique=True)
    value = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Referral Settings"

    def __str__(self):
        return f"{self.key} = {self.value}"