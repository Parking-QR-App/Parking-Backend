from django.db import transaction, IntegrityError, DatabaseError
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import logging
from django.db import models
from django.apps import apps

# Import your API exceptions
from shared.utils.api_exceptions import (
    ValidationException, 
    NotFoundException,
    ServiceUnavailableException,
    ConflictException  # Added missing import
)
from platform_settings.services.import_service import CallBalanceServiceLoader

logger = logging.getLogger(__name__)

class ReferralService:
    """Core referral service handling business logic"""

    _referral_code = None
    _referral_relationship = None
    _referral_settings = None

    @classmethod
    def get_referral_code_model(cls):
        if cls._referral_code is None:
            cls._referral_code = apps.get_model('referral_service', 'ReferralCode')
        return cls._referral_code
    
    @classmethod
    def get_referral_relationship_model(cls):
        if cls._referral_relationship is None:
            cls._referral_relationship = apps.get_model('referral_service', 'ReferralRelationship')
        return cls._referral_relationship
    
    @classmethod
    def get_referral_settings_model(cls):
        if cls._referral_settings is None:
            cls._referral_settings = apps.get_model('referral_service', 'ReferralSettings')
        return cls._referral_settings
    
    @classmethod
    def get_referral_settings(cls, key, default=None):
        """Get referral setting value"""
        if not key or not isinstance(key, str):
            raise ValidationException(
                detail="Invalid settings key",
                context={'key': 'Settings key must be a non-empty string'}
            )
        
        ReferralSettings = cls.get_referral_settings_model()
        try:
            setting = ReferralSettings.objects.get(key=key, is_active=True)
            return setting.value
        except ReferralSettings.DoesNotExist:
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
    def set_referral_settings(cls, key, value, description=""):
        """Update or create referral setting"""
        if not key or not isinstance(key, str):
            raise ValidationException(
                detail="Invalid settings key",
                context={'key': 'Settings key must be a non-empty string'}
            )
        
        if value is None:
            raise ValidationException(
                detail="Invalid settings value",
                context={'value': 'Settings value cannot be None'}
            )
        
        ReferralSettings = cls.get_referral_settings_model()
        try:
            setting, created = ReferralSettings.objects.update_or_create(
                key=key,
                defaults={
                    'value': str(value),
                    'description': description,
                    'is_active': True
                }
            )
            logger.info(f"Setting {'created' if created else 'updated'}: {key}")
            return setting
            
        except DatabaseError as e:
            logger.error(f"Database error setting {key}: {str(e)}")
            raise ServiceUnavailableException(
                detail="Settings database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to set referral setting {key}: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Failed to update referral settings",
                context={'key': key, 'user_message': 'Unable to save settings. Please try again.'}
            )
    
    @classmethod
    def get_default_reward_calls(cls):
        """Get default reward calls from settings"""
        try:
            setting_value = cls.get_referral_settings('default_reward_calls', '5.00')
            return Decimal(str(setting_value))
        except (InvalidOperation, ValueError) as e:
            logger.warning(f"Invalid default_reward_calls setting: {setting_value}, using 5.00")
            return Decimal('5.00')
        except Exception as e:
            logger.warning(f"Failed to get default reward calls: {str(e)}, using default 5.00")
            return Decimal('5.00')
    
    @classmethod
    def get_campaign_reward_calls(cls, campaign_code):
        """Get reward calls for campaign code"""
        if not campaign_code:
            raise ValidationException(
                detail="Invalid campaign code",
                context={'campaign_code': 'Campaign code is required'}
            )
        
        try:
            if hasattr(campaign_code, 'reward_calls') and campaign_code.reward_calls > Decimal('0.00'):
                return campaign_code.reward_calls
            return cls.get_default_reward_calls()
        except Exception as e:
            logger.error(f"Failed to get campaign reward calls: {str(e)}")
            # Fallback to default instead of failing
            return cls.get_default_reward_calls()
    
    @classmethod
    def create_referral_relationship(cls, referrer, referred_user, code):
        """Create a referral or campaign relationship between referrer and referred user."""
        # Input validation
        if not referred_user:
            raise ValidationException(
                detail="Referred user is required",
                context={'referred_user': 'Referred user cannot be None'}
            )
        
        if not code:
            raise ValidationException(
                detail="Referral code is required", 
                context={'code': 'Referral code cannot be None'}
            )

        ReferralRelationship = cls.get_referral_relationship_model()
        
        try:
            # Business logic validation
            if code.code_type == "user":
                if not referrer:
                    raise ValidationException(
                        detail="Referrer is required for referral codes",
                        context={"code": code.code}
                    )
                if referrer.id == referred_user.id:
                    raise ValidationException(
                        detail="User cannot refer themselves",
                        context={"code": code.code}
                    )

            if code.code_type == "campaign":
                referrer = None  # explicitly clear referrer if campaign

            # Check for existing relationship
            existing = ReferralRelationship.objects.filter(
                referred_user=referred_user
            ).first()
            
            if existing:
                raise ConflictException(
                    detail="User already has a referral relationship",
                    context={
                        'referred_user': str(referred_user.id),
                        'existing_code': existing.referral_code.code
                    }
                )

            with transaction.atomic():
                relationship = ReferralRelationship.objects.create(
                    referrer=referrer,
                    referred_user=referred_user,
                    referral_code=code,
                    reward_calls_given=code.reward_calls or 0,
                    status="pending"
                )

                # Increment usage count
                code.usage_count = models.F('usage_count') + 1
                code.save(update_fields=['usage_count'])

            logger.info(
                f"Referral relationship created: "
                f"type={code.code_type}, code={code.code}, "
                f"referrer={referrer.id if referrer else 'campaign'}, "
                f"referred={referred_user.id}"
            )
            return relationship

        except ValidationException:
            raise
        except ConflictException:
            raise
        except IntegrityError as e:
            logger.error(f"Integrity error creating referral relationship: {str(e)}")
            raise ConflictException(
                detail="Referral relationship creation conflict",
                context={'reason': 'Database constraint violation'}
            )
        except DatabaseError as e:
            logger.error(f"Database error creating referral relationship: {str(e)}")
            raise ServiceUnavailableException(
                detail="Referral database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to create referral relationship: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Referral relationship service temporarily unavailable",
                context={
                    'user_message': 'Unable to create referral relationship. Please try again.'
                }
            )
    
    @classmethod
    @transaction.atomic
    def complete_referral(cls, relationship):
        """Complete referral/campaign and give rewards - REGULAR USERS ONLY"""
        if not relationship:
            raise ValidationException(
                detail="Referral relationship is required",
                context={'relationship': 'Relationship cannot be None'}
            )
        
        try:
            CallBalanceService = CallBalanceServiceLoader.get_call_balance_service()
            
            if relationship.status == "completed":
                logger.info(f"Referral relationship {relationship.id} already completed")
                return relationship  # Already completed

            code = relationship.referral_code

            # Determine reward amount
            if code.code_type == "campaign":
                reward_calls = cls.get_campaign_reward_calls(code)
            else:
                reward_calls = cls.get_default_reward_calls()

            # Assign reward based on code type
            if code.code_type == "campaign":
                # Reward referee (new user)
                CallBalanceService.add_referral_reward(relationship.referred_user, reward_calls)
                reward_target = relationship.referred_user
                reward_role = "referred_user"
            else:
                # Reward referrer (existing user)
                CallBalanceService.add_referral_reward(relationship.referrer, reward_calls)
                reward_target = relationship.referrer
                reward_role = "referrer"

            # Update relationship
            relationship.status = "completed"
            relationship.reward_calls_given = reward_calls
            relationship.reward_given_at = timezone.now()
            relationship.save()

            logger.info(
                f"Referral completed: {reward_role} {reward_target.id} "
                f"received {reward_calls} calls (code={code.code}, type={code.code_type})"
            )

            return relationship

        except ValidationException:
            raise
        except DatabaseError as e:
            logger.error(f"Database error completing referral: {str(e)}")
            raise ServiceUnavailableException(
                detail="Referral completion database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to complete referral: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Referral completion service temporarily unavailable",
                context={
                    'user_message': 'Unable to complete referral. Please try again.'
                }
            )
    
    @classmethod
    def get_user_referral_code(cls, user):
        """Get or create user's referral code"""
        if not user:
            raise ValidationException(
                detail="User is required",
                context={'user': 'User cannot be None'}
            )
        
        ReferralCode = cls.get_referral_code_model()
        
        try:
            code = ReferralCode.objects.filter(owner=user, code_type='user').first()
            if not code:
                # Generate new code for user
                code = ReferralCode.objects.create(
                    owner=user,
                    code_type='user',
                    status='active'
                )
                logger.info(f"Created new referral code for user {user.id}: {code.code}")
            return code
            
        except IntegrityError as e:
            logger.error(f"Integrity error creating user referral code: {str(e)}")
            raise ConflictException(
                detail="Referral code creation conflict",
                context={'user_id': str(user.id)}
            )
        except DatabaseError as e:
            logger.error(f"Database error getting user referral code: {str(e)}")
            raise ServiceUnavailableException(
                detail="Referral code database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to get user referral code: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Referral code service temporarily unavailable",
                context={'user_message': 'Unable to load referral code. Please try again.'}
            )
    
    @classmethod
    def validate_referral_code(cls, code_string):
        """Validate a referral code - returns (code, None) or (None, exception)"""
        if not code_string or not isinstance(code_string, str):
            return None, ValidationException(
                detail="Invalid referral code format",
                context={'code': 'Referral code must be a non-empty string'}
            )
        
        ReferralCode = cls.get_referral_code_model()
        
        try:
            code = ReferralCode.objects.get(code=code_string.strip().upper())

            # ADDITIONAL VALIDATION: If it's a user code, owner must be regular
            if code.code_type == 'user' and code.owner:
                return None, ValidationException(
                    detail="Invalid referral code owner",
                    context={'code': code_string}
                )
            
            if not code.is_valid:
                return None, ValidationException(
                    detail="Referral code is not valid or has expired",
                    context={'code': code_string, 'status': code.status}
                )
                
            return code, None
            
        except ReferralCode.DoesNotExist:
            return None, NotFoundException(
                detail="Referral code not found",
                context={'code': code_string}
            )
        except DatabaseError as e:
            logger.error(f"Database error validating referral code: {str(e)}")
            return None, ServiceUnavailableException(
                detail="Referral code validation database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to validate referral code: {str(e)}", exc_info=True)
            return None, ServiceUnavailableException(
                detail="Referral code validation service temporarily unavailable"
            )
    
    @classmethod
    def get_user_referral_stats(cls, user):
        """Get user's referral statistics"""
        if not user:
            raise ValidationException(
                detail="User is required",
                context={'user': 'User cannot be None'}
            )
        
        ReferralRelationship = cls.get_referral_relationship_model()
        
        try:
            referrals_made = ReferralRelationship.objects.filter(
                referrer=user, 
                status='completed'
            ).count()
            
            total_reward = ReferralRelationship.objects.filter(
                referrer=user, 
                status='completed'
            ).aggregate(
                total_reward=models.Sum('reward_calls_given')
            )['total_reward'] or Decimal('0.00')
            
            user_code = cls.get_user_referral_code(user)
            
            return {
                'referrals_made': referrals_made,
                'total_reward_calls': total_reward,
                'active_referral_code': user_code.code
            }
            
        except DatabaseError as e:
            logger.error(f"Database error getting user referral stats: {str(e)}")
            raise ServiceUnavailableException(
                detail="Referral stats database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to get user referral stats: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Referral stats service temporarily unavailable",
                context={'user_message': 'Unable to load referral statistics. Please try again.'}
            )
