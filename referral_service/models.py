from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Index, UniqueConstraint, CheckConstraint, Q
import uuid
import string
import random
from datetime import datetime


def generate_referral_code():
    """Generate a unique 8-character referral code"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


class ReferralCode(models.Model):
    """
    Stores referral codes - both user-generated and admin campaign codes
    """
    CODE_TYPES = [
        ('user', 'User Generated'),
        ('campaign', 'Campaign Code'),
        ('admin', 'Admin Generated'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, default=generate_referral_code)
    
    # Owner (null for campaign codes)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_referral_codes',
        null=True,
        blank=True
    )
    
    # Code metadata
    code_type = models.CharField(max_length=10, choices=CODE_TYPES, default='user')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    
    # Usage tracking
    usage_count = models.PositiveIntegerField(default=0)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)  # null = unlimited
    
    # Time constraints
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)  # null = no expiry
    
    # Analytics fields
    total_registrations = models.PositiveIntegerField(default=0)
    total_verified_users = models.PositiveIntegerField(default=0)
    total_paying_users = models.PositiveIntegerField(default=0)
    total_revenue_generated = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Admin fields
    notes = models.TextField(blank=True)
    created_by_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='created_referral_codes',
        null=True,
        blank=True
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            Index(fields=['code']),
            Index(fields=['owner']),
            Index(fields=['code_type']),
            Index(fields=['status']),
            Index(fields=['created_at']),
            Index(fields=['last_used_at']),
        ]
        constraints = [
            CheckConstraint(
                check=Q(usage_limit__isnull=True) | Q(usage_limit__gte=0),
                name='valid_usage_limit'
            )
        ]

    def __str__(self):
        return f"{self.code} ({self.get_code_type_display()})"

    @property
    def is_valid(self):
        """Check if code is currently valid for use"""
        now = timezone.now()
        return (
            self.status == 'active' and
            self.valid_from <= now and
            (self.valid_until is None or self.valid_until >= now) and
            (self.usage_limit is None or self.usage_count < self.usage_limit)
        )
    
    @property
    def is_expired(self):
        """Returns True if referral code is no longer valid due to expiry"""
        now = timezone.now()
        return (
            self.status == 'expired' or
            (self.valid_until is not None and self.valid_until < now)
        )

    @property
    def conversion_rate(self):
        """Calculate conversion rate from registrations to verified users"""
        if self.total_registrations == 0:
            return 0
        return (self.total_verified_users / self.total_registrations) * 100


class ReferralRelationship(models.Model):
    """
    Tracks who referred whom - the core referral relationship
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('rewarded', 'Rewarded'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # The referral relationship
    referrer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referrals_made'
    )
    referred_user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_source'
    )
    referral_code_used = models.ForeignKey(
        'ReferralCode',
        on_delete=models.CASCADE,
        related_name='relationships'
    )
    
    # Status tracking
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    
    # Verification tracking
    user_verified_at = models.DateTimeField(null=True, blank=True)
    first_payment_at = models.DateTimeField(null=True, blank=True)
    first_payment_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Analytics fields
    registration_ip = models.GenericIPAddressField(null=True, blank=True)
    registration_device_type = models.CharField(max_length=20, blank=True)
    days_to_verify = models.PositiveIntegerField(null=True, blank=True)
    days_to_first_payment = models.PositiveIntegerField(null=True, blank=True)
    
    # Reward tracking
    referrer_rewarded_at = models.DateTimeField(null=True, blank=True)
    referred_user_rewarded_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            Index(fields=['referrer']),
            Index(fields=['referred_user']),
            Index(fields=['referral_code_used']),
            Index(fields=['status']),
            Index(fields=['created_at']),
            Index(fields=['user_verified_at']),
            Index(fields=['first_payment_at']),
        ]
        constraints = [
            UniqueConstraint(fields=['referred_user'], name='unique_referral_per_user'),
            CheckConstraint(
                check=~Q(referrer=models.F('referred_user')),
                name='no_self_referral'
            )
        ]

    def __str__(self):
        return f"{self.referrer} -> {self.referred_user}"


class ReferralLimit(models.Model):
    """
    User-specific referral limits and configurations
    """
    LIMIT_TYPES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('total', 'Total Lifetime'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_limits'
    )
    
    # Limit configurations
    daily_limit = models.PositiveIntegerField(default=10)
    weekly_limit = models.PositiveIntegerField(default=50)
    monthly_limit = models.PositiveIntegerField(default=200)
    total_limit = models.PositiveIntegerField(null=True, blank=True)  # null = unlimited
    
    # Current usage counters (reset by scheduler)
    daily_used = models.PositiveIntegerField(default=0)
    weekly_used = models.PositiveIntegerField(default=0)
    monthly_used = models.PositiveIntegerField(default=0)
    total_used = models.PositiveIntegerField(default=0)
    
    # Reset tracking
    daily_reset_at = models.DateTimeField(auto_now_add=True)
    weekly_reset_at = models.DateTimeField(auto_now_add=True)
    monthly_reset_at = models.DateTimeField(auto_now_add=True)
    
    # Performance tracking
    successful_referrals = models.PositiveIntegerField(default=0)
    verified_referrals = models.PositiveIntegerField(default=0)
    paying_referrals = models.PositiveIntegerField(default=0)
    
    # Admin controls
    is_unlimited = models.BooleanField(default=False)
    is_suspended = models.BooleanField(default=False)
    suspension_reason = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            Index(fields=['user']),
            Index(fields=['is_suspended']),
            Index(fields=['daily_reset_at']),
            Index(fields=['weekly_reset_at']),
            Index(fields=['monthly_reset_at']),
        ]

    def __str__(self):
        return f"Limits for {self.user}"

    @property
    def success_rate(self):
        """Calculate overall referral success rate"""
        if self.total_used == 0:
            return 0
        return (self.verified_referrals / self.total_used) * 100

    def can_refer(self, limit_type='daily'):
        """Check if user can make more referrals based on limit type"""
        if self.is_suspended:
            return False
        
        if self.is_unlimited:
            return True
            
        limits_map = {
            'daily': (self.daily_used, self.daily_limit),
            'weekly': (self.weekly_used, self.weekly_limit),
            'monthly': (self.monthly_used, self.monthly_limit),
            'total': (self.total_used, self.total_limit),
        }
        
        used, limit = limits_map.get(limit_type, (0, 1))
        return limit is None or used < limit
    

class ReferralEvent(models.Model):
    """
    Tracks all referral-related events for detailed analytics
    """
    EVENT_TYPES = [
        ('code_generated', 'Referral Code Generated'),
        ('code_shared', 'Referral Code Shared'),
        ('registration_started', 'Registration Started'),
        ('registration_completed', 'Registration Completed'),
        ('email_verified', 'Email Verified'),
        ('first_payment', 'First Payment Made'),
        ('reward_given', 'Reward Given'),
        ('limit_reached', 'Limit Reached'),
        ('code_expired', 'Code Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Event details
    event_type = models.CharField(max_length=25, choices=EVENT_TYPES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='referral_events'
    )
    referral_code = models.ForeignKey(
        'ReferralCode',
        on_delete=models.CASCADE,
        related_name='events',
        null=True,
        blank=True
    )
    referral_relationship = models.ForeignKey(
        'ReferralRelationship',
        on_delete=models.CASCADE,
        related_name='events',
        null=True,
        blank=True
    )
    
    # Event metadata
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device_type = models.CharField(max_length=20, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            Index(fields=['event_type']),
            Index(fields=['user']),
            Index(fields=['referral_code']),
            Index(fields=['created_at']),
            Index(fields=['event_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.user} - {self.get_event_type_display()}"
    
    
class ReferralLimitHistory(models.Model):
    ACTION_CHOICES = [
        ('set', 'Set Absolute'),
        ('increase', 'Increased'),
        ('decrease', 'Decreased'),
        ('boost', 'Temporary Boost'),
        ('disable', 'Disabled'),
        ('resume', 'Resumed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    limit = models.ForeignKey(
        ReferralLimit,
        on_delete=models.CASCADE,
        related_name='history'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='referral_limit_history_changes'
    )

    previous_daily = models.PositiveIntegerField()
    previous_weekly = models.PositiveIntegerField()
    previous_monthly = models.PositiveIntegerField()
    previous_total = models.PositiveIntegerField(null=True, blank=True)

    new_daily = models.PositiveIntegerField()
    new_weekly = models.PositiveIntegerField()
    new_monthly = models.PositiveIntegerField()
    new_total = models.PositiveIntegerField(null=True, blank=True)

    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['limit', 'action', 'created_at']),
        ]

    def __str__(self):
        return f"LimitHistory({self.limit.user}, action={self.action}, at={self.created_at.isoformat()})"
