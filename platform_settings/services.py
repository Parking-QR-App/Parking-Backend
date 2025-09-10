from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import logging
from django.db import models

from .models import PlatformSetting, UserCallBalance, BalanceResetLog
from auth_service.models import User
from shared.utils.api_exceptions import InsufficientBalanceException

logger = logging.getLogger(__name__)

class SettingsService:
    """
    Central service for accessing platform settings
    """
    
    _cache = {}
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Get a setting value with caching"""
        if key in cls._cache:
            return cls._cache[key]
        
        try:
            setting = PlatformSetting.objects.get(key=key, is_active=True)
            value = setting.value
            cls._cache[key] = value
            return value
        except PlatformSetting.DoesNotExist:
            return default
    
    @classmethod
    def set_setting(cls, key, value):
        """Update a setting value"""
        try:
            setting = PlatformSetting.objects.get(key=key)
            setting.set_value(value)
            setting.save()
            cls._cache[key] = value
            return True
        except PlatformSetting.DoesNotExist:
            return False
    
    # Convenience methods for common settings
    @classmethod
    def get_initial_calls(cls):
        return Decimal(str(cls.get_setting('initial_call_balance', '10.00')))
    
    @classmethod
    def get_reset_amount(cls):
        return Decimal(str(cls.get_setting('cron_reset_amount', '5.00')))
    
    @classmethod
    def get_reset_frequency(cls):
        return cls.get_setting('cron_reset_frequency', 7)
    
    @classmethod
    def get_referral_reward(cls):
        return Decimal(str(cls.get_setting('referral_reward_calls', '5.00')))
    
    @classmethod
    def is_cron_enabled(cls):
        return cls.get_setting('cron_reset_enabled', True)


class CallBalanceService:
    """
    Service for managing user call balances
    """

    @classmethod
    def initialize_user_balance(cls, user):
        """Initialize a user's balance on first login"""
        balance, created = UserCallBalance.objects.get_or_create(
            user=user,
            defaults={
                'base_balance': SettingsService.get_initial_calls(),
                'bonus_balance': Decimal('0.00')
            }
        )
        if created:
            BalanceResetLog.objects.create(
                user=user,
                reset_type='init',
                previous_balance=Decimal('0.00'),
                new_balance=balance.total_balance,
                reset_amount=balance.total_balance,
                notes='Initial balance at registration'
            )
        return balance

    @classmethod
    def get_user_balance(cls, user):
        """Get or create user balance record"""
        balance, _ = UserCallBalance.objects.get_or_create(
            user=user,
            defaults={
                'base_balance': SettingsService.get_initial_calls(),
                'bonus_balance': Decimal('0.00')
            }
        )
        return balance

    @classmethod
    def add_referral_reward(cls, user, reward_amount=None):
        """Add referral reward to user's bonus balance"""
        reward_amount = reward_amount or SettingsService.get_referral_reward()
        balance = cls.get_user_balance(user)

        with transaction.atomic():
            old_total = balance.total_balance
            balance.add_bonus_balance(reward_amount)

            BalanceResetLog.objects.create(
                user=user,
                reset_type='referral',
                previous_balance=old_total,
                new_balance=balance.total_balance,
                reset_amount=reward_amount,
                notes='Referral reward'
            )

        return balance

    # ✅ NEW: centralized deduction method
    @classmethod
    def deduct_call_cost(cls, user, call_cost: Decimal, call=None):
        """
        Deduct a call cost from user's balance.
        Priority: bonus balance first, then base balance.

        Args:
            user (User): The user whose balance will be deducted.
            call_cost (Decimal): The exact cost of the call (must be > 0).
            call (CallRecord, optional): Call record for logging.

        Raises:
            InsufficientBalanceException: If user has insufficient credits.
        """
        if call_cost <= 0:
            raise ValidationException(detail="Call cost must be greater than zero")

        balance = cls.get_user_balance(user)

        with transaction.atomic():
            if balance.total_balance < call_cost:
                # Not enough credits
                raise InsufficientBalanceException(
                    f"User {user.id} has insufficient balance "
                    f"(needed {call_cost}, available {balance.total_balance})"
                )

            # Deduct from bonus first, then base
            deducted_from_bonus = min(call_cost, balance.bonus_balance)
            deducted_from_base = call_cost - deducted_from_bonus

            balance.bonus_balance -= deducted_from_bonus
            balance.base_balance -= deducted_from_base
            balance.save()

            # Optional: update call record if provided
            if call:
                call.deducted_from_bonus = deducted_from_bonus
                call.deducted_from_base = deducted_from_base
                call.deduction_status = "completed"
                call.save(update_fields=[
                    "deducted_from_bonus", "deducted_from_base", "deduction_status"
                ])

            # Log the deduction
            BalanceResetLog.objects.create(
                user=user,
                reset_type="call_deduction",
                previous_balance=balance.total_balance + call_cost,
                new_balance=balance.total_balance,
                reset_amount=call_cost,
                notes=f"Deducted {call_cost} credits for call"
            )

            logger.info(
                f"[CallBalanceService] Deducted {call_cost} from user {user.id} "
                f"(Bonus: {deducted_from_bonus}, Base: {deducted_from_base})"
            )

        return balance

    @classmethod
    def reset_user_balance(cls, user, reset_type='cron'):
        """Reset user's base balance"""
        reset_amount = SettingsService.get_reset_amount()
        balance = cls.get_user_balance(user)

        with transaction.atomic():
            old_total = balance.total_balance
            balance.set_base_balance(reset_amount)

            BalanceResetLog.objects.create(
                user=user,
                reset_type=reset_type,
                previous_balance=old_total,
                new_balance=balance.total_balance,
                reset_amount=reset_amount,
                notes=f'{reset_type} reset'
            )

        return balance

    @classmethod
    def get_users_for_reset(cls):
        """Get users who need balance reset"""
        if not SettingsService.is_cron_enabled():
            return []

        frequency_days = SettingsService.get_reset_frequency()
        cutoff_date = timezone.now() - timezone.timedelta(days=frequency_days)

        return User.objects.filter(
            models.Q(call_balance_info__last_reset__lt=cutoff_date) |
            models.Q(call_balance_info__last_reset__isnull=True)
        )

    @classmethod
    def execute_cron_reset(cls):
        """Execute automated balance reset"""
        if not SettingsService.is_cron_enabled():
            return {'success': False, 'message': 'Cron reset disabled'}

        users_to_reset = cls.get_users_for_reset()
        reset_count = 0

        for user in users_to_reset:
            try:
                cls.reset_user_balance(user)
                reset_count += 1
            except Exception as e:
                logger.error(f"Failed to reset user {user.id}: {str(e)}")

        return {
            'success': True,
            'reset_count': reset_count,
            'total_users': len(users_to_reset)
        }



class DefaultSettings:
    """
    Initialize default platform settings
    """
    DEFAULT_SETTINGS = [
        # Call Management
        {
            'key': 'initial_call_balance',
            'display_name': 'Initial Call Balance',
            'description': 'Calls given to new users on registration',
            'category': 'call_management',
            'setting_type': 'decimal',
            'decimal_value': Decimal('10.00')
        },
        {
            'key': 'cron_reset_enabled',
            'display_name': 'Cron Reset Enabled',
            'description': 'Enable automatic call balance resets',
            'category': 'call_management',
            'setting_type': 'boolean',
            'boolean_value': True
        },
        {
            'key': 'cron_reset_frequency',
            'display_name': 'Reset Frequency (Days)',
            'description': 'How often to reset balances (7 = weekly)',
            'category': 'call_management',
            'setting_type': 'integer',
            'integer_value': 7
        },
        {
            'key': 'cron_reset_amount',
            'display_name': 'Reset Amount',
            'description': 'Calls to set during reset',
            'category': 'call_management',
            'setting_type': 'decimal',
            'decimal_value': Decimal('5.00')
        },
        
        # Referral System
        {
            'key': 'referral_reward_calls',
            'display_name': 'Referral Reward Calls',
            'description': 'Calls given for successful referrals',
            'category': 'referral_system',
            'setting_type': 'decimal',
            'decimal_value': Decimal('5.00')
        },
    ]
    
    @classmethod
    def initialize(cls):
        """Create default settings if they don't exist"""
        created = 0
        for setting_data in cls.DEFAULT_SETTINGS:
            obj, created_flag = PlatformSetting.objects.get_or_create(
                key=setting_data['key'],
                defaults=setting_data
            )
            if created_flag:
                created += 1
        return created