from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.db.models import Q, F, CheckConstraint, Index
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
import uuid
from decimal import Decimal


class RewardTriggerType(models.TextChoices):
    REGISTRATION = 'registration', 'User Registration'
    EMAIL_VERIFICATION = 'email_verification', 'Email Verification'
    FIRST_PAYMENT = 'first_payment', 'First Payment'
    PAYMENT_MILESTONE = 'payment_milestone', 'Payment Milestone'
    REFERRAL_MILESTONE = 'referral_milestone', 'Referral Milestone'


class RewardType(models.TextChoices):
    FREE_CALLS = 'free_calls', 'Free Call Minutes'
    CASHBACK = 'cashback', 'Cashback Amount'
    DISCOUNT = 'discount', 'Discount Percentage'
    BONUS_CREDITS = 'bonus_credits', 'Bonus Credits'
    PREMIUM = 'premium_features', 'Premium Features Access'


class RecipientType(models.TextChoices):
    REFERRER = 'referrer', 'Referrer Only'
    REFERRED = 'referred', 'Referred User Only'
    BOTH = 'both', 'Both Referrer and Referred'


class RewardConfiguration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    trigger_type = models.CharField(max_length=30, choices=RewardTriggerType.choices)
    reward_type = models.CharField(max_length=30, choices=RewardType.choices)
    recipient_type = models.CharField(max_length=10, choices=RecipientType.choices)

    reward_value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.0'))])
    max_reward_value = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    minimum_payment_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    milestone_count = models.PositiveIntegerField(null=True, blank=True)

    max_uses_per_user = models.PositiveIntegerField(null=True, blank=True)
    max_total_uses = models.PositiveIntegerField(null=True, blank=True)
    current_total_uses = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)

    priority = models.PositiveIntegerField(default=1)

    total_rewards_given = models.PositiveIntegerField(default=0)
    total_value_distributed = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_reward_configs"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', '-created_at']
        indexes = [
            Index(fields=['trigger_type', 'reward_type']),
            Index(fields=['priority', 'is_active']),
            Index(fields=['valid_from', 'valid_until']),
        ]
        constraints = [
            CheckConstraint(check=Q(max_reward_value__isnull=True) | Q(max_reward_value__gte=F('reward_value')),
                            name='valid_max_value'),
        ]

    @property
    def is_valid(self):
        now = timezone.now()
        return (
            self.is_active and
            self.valid_from <= now and
            (self.valid_until is None or self.valid_until >= now) and
            (self.max_total_uses is None or self.current_total_uses < self.max_total_uses)
        )

    def __str__(self):
        return f"{self.name} ({self.get_trigger_type_display()})"


class UserReward(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('used', 'Used'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_rewards')
    reward_config = models.ForeignKey(RewardConfiguration, on_delete=models.CASCADE, related_name='rewards')

    # Optional: Connect to a referral or any trigger object using GenericForeignKey
    trigger_content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    trigger_object_id = models.UUIDField(null=True, blank=True)
    trigger_object = GenericForeignKey('trigger_content_type', 'trigger_object_id')

    trigger_event = models.CharField(max_length=50)

    original_value = models.DecimalField(max_digits=10, decimal_places=2)
    reward_value = models.DecimalField(max_digits=10, decimal_places=2)
    used_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remaining_value = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    expires_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)

    metadata = models.JSONField(default=dict, blank=True)
    usage_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            Index(fields=['user', 'status']),
            Index(fields=['reward_config']),
            Index(fields=['trigger_event']),
            Index(fields=['created_at']),
        ]
        constraints = [
            CheckConstraint(check=Q(used_value__lte=F('reward_value')), name='used_lte_reward'),
        ]

    def save(self, *args, **kwargs):
        self.remaining_value = self.reward_value - self.used_value
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        now = timezone.now()
        return (
            self.status == 'active' and
            self.remaining_value > 0 and
            (self.expires_at is None or self.expires_at >= now)
        )

    def __str__(self):
        return f"{self.user} | {self.reward_config.name} | {self.status}"


class RewardTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('activation', 'Reward Activation'),
        ('usage', 'Reward Usage'),
        ('partial_usage', 'Partial Usage'),
        ('expiry', 'Reward Expiry'),
        ('cancellation', 'Reward Cancellation'),
        ('adjustment', 'Value Adjustment'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_reward = models.ForeignKey(UserReward, on_delete=models.CASCADE, related_name='transactions')

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance_before = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)

    related_payment = models.UUIDField(null=True, blank=True)  # Can later be FK to Payment model
    related_call_session = models.CharField(max_length=255, blank=True)

    description = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reward_transactions'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [Index(fields=['user_reward', 'transaction_type'])]

    def __str__(self):
        return f"{self.user_reward} | {self.transaction_type} | {self.amount}"


class RewardUsageLimit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reward_limits')

    # Limits
    daily_cashback_limit = models.DecimalField(max_digits=10, decimal_places=2, default=100)
    weekly_cashback_limit = models.DecimalField(max_digits=10, decimal_places=2, default=500)
    monthly_cashback_limit = models.DecimalField(max_digits=10, decimal_places=2, default=2000)

    daily_calls_limit = models.PositiveIntegerField(default=60)
    weekly_calls_limit = models.PositiveIntegerField(default=300)
    monthly_calls_limit = models.PositiveIntegerField(default=1200)

    # Usage
    daily_cashback_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    weekly_cashback_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monthly_cashback_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    daily_calls_used = models.PositiveIntegerField(default=0)
    weekly_calls_used = models.PositiveIntegerField(default=0)
    monthly_calls_used = models.PositiveIntegerField(default=0)

    daily_reset_at = models.DateTimeField(auto_now_add=True)
    weekly_reset_at = models.DateTimeField(auto_now_add=True)
    monthly_reset_at = models.DateTimeField(auto_now_add=True)

    is_unlimited = models.BooleanField(default=False)
    custom_limits = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def can_use_cashback(self, amount, period='daily'):
        if self.is_unlimited:
            return True
        used, limit = {
            'daily': (self.daily_cashback_used, self.daily_cashback_limit),
            'weekly': (self.weekly_cashback_used, self.weekly_cashback_limit),
            'monthly': (self.monthly_cashback_used, self.monthly_cashback_limit),
        }.get(period, (0, Decimal('0')))
        return used + amount <= limit

    def can_use_calls(self, minutes, period='daily'):
        if self.is_unlimited:
            return True
        used, limit = {
            'daily': (self.daily_calls_used, self.daily_calls_limit),
            'weekly': (self.weekly_calls_used, self.weekly_calls_limit),
            'monthly': (self.monthly_calls_used, self.monthly_calls_limit),
        }.get(period, (0, 0))
        return used + minutes <= limit

    def __str__(self):
        return f"Limits for {self.user}"
