from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import logging
from .models import ReferralCode, ReferralRelationship, ReferralSettings, generate_referral_code
from django.db import models

# Import your API exceptions
from shared.utils.api_exceptions import (
    ValidationException, NotFoundException,
    ServiceUnavailableException
)

logger = logging.getLogger(__name__)

class ReferralService:
    """
    Core referral service handling business logic
    """
    
    @classmethod
    def get_referral_settings(cls, key, default=None):
        """Get referral setting value"""
        try:
            setting = ReferralSettings.objects.get(key=key, is_active=True)
            return setting.value
        except ReferralSettings.DoesNotExist:
            return default
    
    @classmethod
    def set_referral_settings(cls, key, value, description=""):
        """Update or create referral setting"""
        try:
            setting, created = ReferralSettings.objects.update_or_create(
                key=key,
                defaults={'value': value, 'description': description}
            )
            return setting
        except Exception as e:
            logger.error(f"Failed to set referral setting {key}: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to update referral settings",
                context={'key': key, 'error': str(e)}
            )
    
    @classmethod
    def get_default_reward_calls(cls):
        """Get default reward calls from settings"""
        try:
            return Decimal(cls.get_referral_settings('default_reward_calls', '5.00'))
        except Exception as e:
            logger.warning(f"Failed to get default reward calls: {str(e)}, using default 5.00")
            return Decimal('5.00')
    
    @classmethod
    def get_campaign_reward_calls(cls, campaign_code):
        """Get reward calls for campaign code"""
        try:
            if campaign_code.reward_calls > Decimal('0.00'):
                return campaign_code.reward_calls
            return cls.get_default_reward_calls()
        except Exception as e:
            logger.error(f"Failed to get campaign reward calls: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to get campaign reward amount",
                context={'campaign_code': campaign_code.code, 'error': str(e)}
            )
    
    @classmethod
    def create_referral_relationship(cls, referrer, referred_user, code):
        """
        Create a referral or campaign relationship between referrer and referred user.
        - For referral codes: requires a valid referrer
        - For campaign codes: referrer is None
        """
        try:
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
        except Exception as e:
            logger.error(f"Failed to create referral relationship: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to create referral relationship",
                context={"referrer": str(referrer.id) if referrer else None,
                         "referred": str(referred_user.id),
                         "code": code.code,
                         "error": str(e)}
            )
    
    @classmethod
    @transaction.atomic
    def complete_referral(cls, relationship):
        """Complete referral/campaign and give rewards"""
        try:
            from importlib import import_module
            CallBalanceService = import_module('platform_settings.services').CallBalanceService
            try:
                
                if relationship.status == "completed":
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

            except Exception as e:
                logger.error(f"Failed to complete referral: {str(e)}")
                raise ServiceUnavailableException(
                    detail="Failed to complete referral",
                    context={
                        "relationship_id": str(relationship.id),
                        "code": relationship.referral_code.code,
                        "error": str(e),
                    },
                )
        except ImportError as e:
            logger.error(f"Failed to import CallBalanceService: {str(e)}")
            raise ServiceUnavailableException(
                detail="Service temporarily unavailable",
                context={'error': 'Call balance service not available'}
            )
    
    @classmethod
    def get_user_referral_code(cls, user):
        """Get or create user's referral code"""
        try:
            code = ReferralCode.objects.filter(owner=user, code_type='user').first()
            if not code:
                code = ReferralCode.objects.create(
                    owner=user,
                    code_type='user',
                    status='active'
                )
            return code
        except Exception as e:
            logger.error(f"Failed to get user referral code: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to get user referral code",
                context={'user_id': str(user.id), 'error': str(e)}
            )
    
    @classmethod
    def validate_referral_code(cls, code_string):
        """Validate a referral code"""
        try:
            code = ReferralCode.objects.get(code=code_string)
            if not code.is_valid:
                return None, ValidationException(
                    detail="Referral code is not valid or has expired",
                    context={'referral_code': code_string}
                )
            return code, None
        except ReferralCode.DoesNotExist:
            return None, NotFoundException(
                detail="Referral code not found",
                context={'referral_code': code_string}
            )
        except Exception as e:
            logger.error(f"Failed to validate referral code: {str(e)}")
            return None, ServiceUnavailableException(
                detail="Failed to validate referral code",
                context={'referral_code': code_string, 'error': str(e)}
            )
    
    @classmethod
    def get_user_referral_stats(cls, user):
        """Get user's referral statistics"""
        try:
            referrals_made = ReferralRelationship.objects.filter(referrer=user, status='completed').count()
            total_reward = ReferralRelationship.objects.filter(
                referrer=user, 
                status='completed'
            ).aggregate(total_reward=models.Sum('reward_calls_given'))['total_reward'] or Decimal('0.00')
            
            return {
                'referrals_made': referrals_made,
                'total_reward_calls': total_reward,
                'active_referral_code': cls.get_user_referral_code(user).code
            }
        except Exception as e:
            logger.error(f"Failed to get user referral stats: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to get referral statistics",
                context={'user_id': str(user.id), 'error': str(e)}
            )
    

class CampaignService:
    """
    Service for managing campaign codes
    """
    
    @classmethod
    def create_campaign_code(cls, code_data, created_by=None):
        """Create a new campaign referral code"""
        try:
            with transaction.atomic():
                code = ReferralCode.objects.create(
                    code=code_data.get('code') or generate_referral_code(),
                    code_type='campaign',
                    status=code_data.get('status', 'active'),
                    max_usage=code_data.get('max_usage', 0),
                    valid_from=code_data.get('valid_from', timezone.now()),
                    valid_until=code_data.get('valid_until'),
                    reward_calls=Decimal(str(code_data.get('reward_calls', 0))),
                )
            return code
        except Exception as e:
            logger.error(f"Failed to create campaign code: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to create campaign code",
                context={'code_data': code_data, 'error': str(e)}
            )
    
    @classmethod
    def get_active_campaigns(cls):
        """Get all active campaign codes"""
        try:
            now = timezone.now()
            return ReferralCode.objects.filter(
                code_type='campaign',
                status='active',
                valid_from__lte=now
            ).filter(
                models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=now)
            )
        except Exception as e:
            logger.error(f"Failed to get active campaigns: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to get active campaigns",
                context={'error': str(e)}
            )
        
    @classmethod
    def deactivate_campaign_code(cls, code_id):
        """Deactivate a campaign code"""
        try:
            code = ReferralCode.objects.get(id=code_id, code_type='campaign')
            code.status = 'inactive'
            code.save()
            return code
        except ReferralCode.DoesNotExist:
            raise NotFoundException(
                detail="Campaign code not found",
                context={'code_id': str(code_id)}
            )
        except Exception as e:
            logger.error(f"Failed to deactivate campaign code: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to deactivate campaign code",
                context={'code_id': str(code_id), 'error': str(e)}
            )