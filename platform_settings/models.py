from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal
import uuid

class PlatformSetting(models.Model):
    """
    Dynamic configuration system - Admin controls everything here
    """
    SETTING_TYPES = [
        ('boolean', 'Boolean'),
        ('integer', 'Integer'),
        ('decimal', 'Decimal'),
        ('string', 'String'),
    ]

    CATEGORIES = [
        ('call_management', 'Call Management'),
        ('referral_system', 'Referral System'),
        ('automation', 'Automation'),
    ]

    key = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, choices=CATEGORIES)
    setting_type = models.CharField(max_length=20, choices=SETTING_TYPES)
    
    # Value storage based on type
    string_value = models.CharField(max_length=500, blank=True, null=True)
    integer_value = models.IntegerField(blank=True, null=True)
    decimal_value = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    boolean_value = models.BooleanField(blank=True, null=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'display_name']

    def __str__(self):
        return f"{self.display_name} ({self.key})"

    @property
    def value(self):
        """Get the actual value based on setting type"""
        if self.setting_type == 'boolean':
            return self.boolean_value
        elif self.setting_type == 'integer':
            return self.integer_value
        elif self.setting_type == 'decimal':
            return self.decimal_value
        else:
            return self.string_value

    def set_value(self, value):
        """Set value based on setting type"""
        if self.setting_type == 'boolean':
            self.boolean_value = bool(value)
        elif self.setting_type == 'integer':
            self.integer_value = int(value)
        elif self.setting_type == 'decimal':
            self.decimal_value = Decimal(str(value))
        else:
            self.string_value = str(value)


class UserCallBalance(models.Model):
    """
    User-specific call balance with base/bonus separation
    Solves the referral reward preservation problem
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='call_balance_info'
    )
    
    # Base balance - gets reset by cron jobs
    base_balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    # Bonus balance - from referrals, never reset
    bonus_balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    last_reset = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "User Call Balances"

    def __str__(self):
        return f"{self.user.email} - Total: {self.total_balance}"

    @property
    def total_balance(self):
        """Total available calls"""
        return self.base_balance + self.bonus_balance

    def add_bonus_balance(self, amount):
        """Add to bonus balance (referrals, purchases)"""
        self.bonus_balance += Decimal(str(amount))
        self.save()

    def set_base_balance(self, amount):
        """Set base balance (used by cron resets)"""
        self.base_balance = Decimal(str(amount))
        self.last_reset = timezone.now()
        self.save()


class BalanceResetLog(models.Model):
    """
    Audit trail for all balance changes
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reset_type = models.CharField(max_length=20, choices=[
        ('cron', 'Cron Job'),
        ('admin', 'Admin Manual'),
        ('referral', 'Referral Reward'),
    ])
    previous_balance = models.DecimalField(max_digits=10, decimal_places=2)
    new_balance = models.DecimalField(max_digits=10, decimal_places=2)
    reset_amount = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']