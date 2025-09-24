from django.utils import timezone
from django.db import transaction, DatabaseError, IntegrityError
from decimal import Decimal, InvalidOperation
import logging
from django.db import models
from functools import wraps
from django.apps import apps
from shared.utils.api_exceptions import (
    ValidationException, 
    ServiceUnavailableException, 
    InsufficientBalanceException,
    NotFoundException,
    ConflictException  # Added missing import
)

logger = logging.getLogger(__name__)

class SettingsService:
    """Central service for accessing platform settings"""
    
    _cache = {}
    _platform_setting = None

    @classmethod
    def get_platform_setting_model(cls):
        if cls._platform_setting is None:
            cls._platform_setting = apps.get_model('platform_settings', 'PlatformSetting')
        return cls._platform_setting
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Get a setting value with caching"""
        if not key or not isinstance(key, str):
            raise ValidationException(
                detail="Invalid setting key",
                context={'key': 'Setting key must be a non-empty string'}
            )
        
        PlatformSetting = cls.get_platform_setting_model()
        
        if key in cls._cache:
            return cls._cache[key]
        
        try:
            setting = PlatformSetting.objects.get(key=key, is_active=True)
            value = setting.value
            cls._cache[key] = value
            return value
        except PlatformSetting.DoesNotExist:
            return default
        except DatabaseError as e:
            logger.error(f"Database error getting setting {key}: {str(e)}")
            raise ServiceUnavailableException(
                detail="Settings database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Unexpected error getting setting {key}: {str(e)}", exc_info=True)
            return default  # Graceful fallback for settings
    
    @classmethod
    def set_setting(cls, key, value):
        """Update a setting value"""
        if not key or not isinstance(key, str):
            raise ValidationException(
                detail="Invalid setting key",
                context={'key': 'Setting key must be a non-empty string'}
            )
        
        if value is None:
            raise ValidationException(
                detail="Invalid setting value",
                context={'value': 'Setting value cannot be None'}
            )
        
        PlatformSetting = cls.get_platform_setting_model()
        
        try:
            setting = PlatformSetting.objects.get(key=key)
            setting.set_value(value)
            setting.save()
            cls._cache[key] = value
            logger.info(f"Updated setting {key}")
            return True
        except PlatformSetting.DoesNotExist:
            raise NotFoundException(
                detail="Setting not found",
                context={'key': f'No setting found with key: {key}'}
            )
        except DatabaseError as e:
            logger.error(f"Database error updating setting {key}: {str(e)}")
            raise ServiceUnavailableException(
                detail="Settings database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to update setting {key}: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Settings update service temporarily unavailable"
            )
    
    # Convenience methods with error handling
    @classmethod
    def get_initial_calls(cls):
        try:
            return Decimal(str(cls.get_setting('initial_call_balance', '10.00')))
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Invalid initial_call_balance setting, using default: {str(e)}")
            return Decimal('10.00')
    
    @classmethod
    def get_reset_amount(cls):
        try:
            return Decimal(str(cls.get_setting('cron_reset_amount', '5.00')))
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Invalid cron_reset_amount setting, using default: {str(e)}")
            return Decimal('5.00')
    
    @classmethod
    def get_reset_frequency(cls):
        try:
            return int(cls.get_setting('cron_reset_frequency', 7))
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid cron_reset_frequency setting, using default: {str(e)}")
            return 7
    
    @classmethod
    def is_cron_enabled(cls):
        try:
            setting = cls.get_setting('cron_reset_enabled', True)
            return bool(setting) if setting is not None else True
        except Exception as e:
            logger.warning(f"Error getting cron_reset_enabled setting, using default: {str(e)}")
            return True

class CallBalanceService:
    """Service for managing user call balances"""
    
    _balance_reset_log = None
    _user_call_balance = None
    _referral_settings = None
    _user_model = None

    @classmethod
    def get_balance_reset_log_model(cls):
        if cls._balance_reset_log is None:
            cls._balance_reset_log = apps.get_model('platform_settings', 'BalanceResetLog')
        return cls._balance_reset_log

    @classmethod
    def get_user_call_balance_model(cls):
        if cls._user_call_balance is None:
            cls._user_call_balance = apps.get_model('platform_settings', 'UserCallBalance')
        return cls._user_call_balance

    @classmethod
    def get_referral_settings_model(cls):
        if cls._referral_settings is None:
            cls._referral_settings = apps.get_model('referral_service', 'ReferralSettings')
        return cls._referral_settings
    
    @classmethod
    def get_user_model(cls):
        if cls._user_model is None:
            cls._user_model = apps.get_model('auth_service', 'User')
        return cls._user_model

    @classmethod
    def get_referral_settings(cls, key, default=None):
        """Get referral setting value using Django's app registry"""
        if not key or not isinstance(key, str):
            return default
        
        ReferralSettings = cls.get_referral_settings_model()
        
        try:
            setting = ReferralSettings.objects.get(key=key, is_active=True)
            return setting.value
        except ReferralSettings.DoesNotExist:
            return default
        except DatabaseError as e:
            logger.error(f"Database error fetching referral setting {key}: {str(e)}")
            return default
        except Exception as e:
            logger.error(f"Error fetching referral setting {key}: {str(e)}")
            return default

    @classmethod
    def initialize_user_balance(cls, user):
        """Initialize a user's balance on first login"""
        UserCallBalance = cls.get_user_call_balance_model()
        BalanceResetLog = cls.get_balance_reset_log_model()

        try:
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
                logger.info(f"Initialized balance for user {user.id}")
            
            return balance
            
        except IntegrityError as e:
            logger.error(f"Integrity error initializing balance for user {user.id}: {str(e)}")
            raise ConflictException(
                detail="Balance initialization conflict",
                context={'user_id': str(user.id)}
            )
        except DatabaseError as e:
            logger.error(f"Database error initializing balance for user {user.id}: {str(e)}")
            raise ServiceUnavailableException(
                detail="Balance initialization database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to initialize balance for user {user.id}: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Balance initialization service temporarily unavailable"
            )

    @classmethod
    def get_user_balance(cls, user):
        """Get or create user balance"""
        UserCallBalance = cls.get_user_call_balance_model()

        try:
            balance, created = UserCallBalance.objects.get_or_create(
                user=user,
                defaults={
                    'base_balance': SettingsService.get_initial_calls(),
                    'bonus_balance': Decimal('0.00')
                }
            )
            return balance
        except DatabaseError as e:
            logger.error(f"Database error getting balance for user {user.id}: {str(e)}")
            raise ServiceUnavailableException(
                detail="User balance database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to get balance for user {user.id}: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="User balance service temporarily unavailable"
            )

    @classmethod
    def add_referral_reward(cls, user, reward_amount=None):
        """Add referral reward to user's bonus balance"""
        # Input validation
        if reward_amount is not None:
            try:
                reward_amount = Decimal(str(reward_amount))
                if reward_amount <= 0:
                    raise ValidationException(
                        detail="Invalid reward amount",
                        context={'reward_amount': 'Reward amount must be positive'}
                    )
            except (InvalidOperation, ValueError):
                raise ValidationException(
                    detail="Invalid reward amount format",
                    context={'reward_amount': 'Reward amount must be a valid decimal number'}
                )

        BalanceResetLog = cls.get_balance_reset_log_model()
        
        try:
            if reward_amount is None:
                reward_value = cls.get_referral_settings('default_reward_calls', '5.00')
                try:
                    reward_amount = Decimal(str(reward_value))
                except (InvalidOperation, ValueError):
                    reward_amount = Decimal('5.00')
                    logger.warning(f"Invalid reward amount from settings: {reward_value}, using default 5.00")

            balance = cls.get_user_balance(user)

            with transaction.atomic():
                old_total = balance.total_balance
                balance.add_bonus_balance(reward_amount)
                balance.save()

                BalanceResetLog.objects.create(
                    user=user,
                    reset_type='referral',
                    previous_balance=old_total,
                    new_balance=balance.total_balance,
                    reset_amount=reward_amount,
                    notes='Referral reward added'
                )

            logger.info(f"Added {reward_amount} referral reward to user {user.id}")
            return balance

        except ValidationException:
            raise
        except DatabaseError as e:
            logger.error(f"Database error adding referral reward for user {user.id}: {str(e)}")
            raise ServiceUnavailableException(
                detail="Referral reward database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to add referral reward for user {user.id}: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Referral reward service temporarily unavailable",
                context={'user_message': 'Unable to add referral reward. Please try again.'}
            )
        
    @classmethod
    def deduct_call_cost(cls, user, call_cost, call=None):
        """Deduct a call cost from user's balance"""
        # Input validation
        if not call_cost:
            raise ValidationException(
                detail="Call cost is required",
                context={'call_cost': 'Call cost cannot be None or zero'}
            )
        
        try:
            call_cost = Decimal(str(call_cost))
            if call_cost <= 0:
                raise ValidationException(
                    detail="Invalid call cost",
                    context={'call_cost': 'Call cost must be greater than zero'}
                )
        except (InvalidOperation, ValueError):
            raise ValidationException(
                detail="Invalid call cost format",
                context={'call_cost': 'Call cost must be a valid decimal number'}
            )

        BalanceResetLog = cls.get_balance_reset_log_model()

        try:
            balance = cls.get_user_balance(user)

            with transaction.atomic():
                if balance.total_balance < call_cost:
                    raise InsufficientBalanceException(
                        detail="Insufficient call balance",
                        context={
                            'required': str(call_cost),
                            'available': str(balance.total_balance),
                            'user_id': str(user.id)
                        }
                    )

                # Deduct from bonus first, then base
                deducted_from_bonus = min(call_cost, balance.bonus_balance)
                deducted_from_base = call_cost - deducted_from_bonus

                balance.bonus_balance -= deducted_from_bonus
                balance.base_balance -= deducted_from_base
                balance.save()

                # Update call record if provided
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
                f"Deducted {call_cost} from user {user.id} "
                f"(Bonus: {deducted_from_bonus}, Base: {deducted_from_base})"
            )

            return balance

        except ValidationException:
            raise
        except InsufficientBalanceException:
            raise
        except DatabaseError as e:
            logger.error(f"Database error deducting call cost for user {user.id}: {str(e)}")
            raise ServiceUnavailableException(
                detail="Call deduction database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to deduct call cost for user {user.id}: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Call deduction service temporarily unavailable"
            )

    @classmethod
    def reset_user_balance(cls, user, reset_type='cron'):
        """Reset user's base balance"""
        if reset_type not in ['cron', 'manual', 'admin']:
            raise ValidationException(
                detail="Invalid reset type",
                context={'reset_type': 'Reset type must be one of: cron, manual, admin'}
            )

        BalanceResetLog = cls.get_balance_reset_log_model()
        
        try:
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

            logger.info(f"Reset balance for user {user.id} (type: {reset_type})")
            return balance

        except DatabaseError as e:
            logger.error(f"Database error resetting balance for user {user.id}: {str(e)}")
            raise ServiceUnavailableException(
                detail="Balance reset database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to reset balance for user {user.id}: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Balance reset service temporarily unavailable"
            )

    @classmethod
    def get_users_for_reset(cls):
        """Get users who need balance reset"""
        User = cls.get_user_model()

        try:
            if not SettingsService.is_cron_enabled():
                return []

            frequency_days = SettingsService.get_reset_frequency()
            cutoff_date = timezone.now() - timezone.timedelta(days=frequency_days)

            return User.objects.filter(
                is_staff=False,
                is_active=True
            ).filter(
                models.Q(call_balance_info__last_reset__lt=cutoff_date) |
                models.Q(call_balance_info__last_reset__isnull=True)
            )
        except DatabaseError as e:
            logger.error(f"Database error getting users for reset: {str(e)}")
            raise ServiceUnavailableException(
                detail="User lookup database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to get users for reset: {str(e)}", exc_info=True)
            return []  # Graceful fallback for cron operations

    @classmethod
    def execute_cron_reset(cls):
        """Execute automated balance reset"""
        try:
            if not SettingsService.is_cron_enabled():
                return {'success': False, 'message': 'Cron reset disabled'}

            users_to_reset = cls.get_users_for_reset()
            reset_count = 0
            failed_count = 0

            for user in users_to_reset:
                try:
                    cls.reset_user_balance(user)
                    reset_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Failed to reset user {user.id}: {str(e)}")

            logger.info(f"Cron reset completed: {reset_count} successful, {failed_count} failed")

            return {
                'success': True,
                'reset_count': reset_count,
                'failed_count': failed_count,
                'total_users': len(users_to_reset)
            }
        except Exception as e:
            logger.error(f"Cron reset execution failed: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Automated reset service temporarily unavailable"
            )

class DefaultSettings:
    """Initialize default platform settings"""
    
    _platform_setting = None

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
    def get_platform_setting_model(cls):
        if cls._platform_setting is None:
            cls._platform_setting = apps.get_model('platform_settings', 'PlatformSetting')
        return cls._platform_setting
    
    @classmethod
    def initialize(cls):
        """Create default settings if they don't exist"""
        PlatformSetting = cls.get_platform_setting_model()
        created = 0
        
        try:
            for setting_data in cls.DEFAULT_SETTINGS:
                obj, created_flag = PlatformSetting.objects.get_or_create(
                    key=setting_data['key'],
                    defaults=setting_data
                )
                if created_flag:
                    created += 1
                    logger.info(f"Created default setting: {setting_data['key']}")
            
            return created
            
        except DatabaseError as e:
            logger.error(f"Database error initializing default settings: {str(e)}")
            raise ServiceUnavailableException(
                detail="Settings initialization database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to initialize default settings: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Settings initialization service temporarily unavailable"
            )
