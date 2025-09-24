from django.db import transaction, IntegrityError, DatabaseError
from django.utils import timezone
from decimal import Decimal, InvalidOperation
import logging
from django.apps import apps
import importlib

# Import your API exceptions
from shared.utils.api_exceptions import (
    NotFoundException,
    ServiceUnavailableException,
    ValidationException,
    ConflictException  # Added missing import
)

logger = logging.getLogger(__name__)

class CampaignService:
    """Service for managing campaign codes"""
    _referral_code = None
    _generate_referral_code = None

    @classmethod
    def get_referral_code_model(cls):
        if cls._referral_code is None:
            cls._referral_code = apps.get_model('referral_service', 'ReferralCode')
        return cls._referral_code

    @classmethod
    def get_generate_referral_code(cls):
        if cls._generate_referral_code is None:
            module = importlib.import_module('referral_service.models')
            cls._generate_referral_code = getattr(module, 'generate_referral_code')
        return cls._generate_referral_code
    
    @classmethod
    def create_campaign_code(cls, code_data, created_by=None):
        """Create a new campaign referral code"""
        # Input validation
        if not code_data or not isinstance(code_data, dict):
            raise ValidationException(
                detail="Invalid campaign code data",
                context={'code_data': 'Campaign data must be a valid dictionary'}
            )
        
        # Validate reward_calls
        reward_calls_value = code_data.get('reward_calls', 0)
        try:
            reward_calls = Decimal(str(reward_calls_value))
            if reward_calls < 0:
                raise ValidationException(
                    detail="Invalid reward calls value",
                    context={'reward_calls': 'Reward calls must be non-negative'}
                )
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationException(
                detail="Invalid reward calls format",
                context={'reward_calls': 'Reward calls must be a valid decimal number'}
            )
        
        # Validate max_usage
        max_usage = code_data.get('max_usage', 0)
        if not isinstance(max_usage, int) or max_usage < 0:
            raise ValidationException(
                detail="Invalid max usage value",
                context={'max_usage': 'Max usage must be a non-negative integer'}
            )
        
        # Validate dates
        valid_from = code_data.get('valid_from', timezone.now())
        valid_until = code_data.get('valid_until')
        
        if valid_until and valid_from and valid_until <= valid_from:
            raise ValidationException(
                detail="Invalid date range",
                context={'dates': 'Valid until must be after valid from date'}
            )

        ReferralCode = cls.get_referral_code_model()
        generate_referral_code = cls.get_generate_referral_code()

        try:
            with transaction.atomic():
                # Generate or validate custom code
                custom_code = code_data.get('code')
                if custom_code:
                    # Validate custom code format
                    if not isinstance(custom_code, str) or len(custom_code.strip()) < 3:
                        raise ValidationException(
                            detail="Invalid custom code format",
                            context={'code': 'Custom code must be at least 3 characters long'}
                        )
                    final_code = custom_code.strip().upper()
                else:
                    final_code = generate_referral_code()

                code = ReferralCode.objects.create(
                    code=final_code,
                    code_type='campaign',
                    status=code_data.get('status', 'active'),
                    max_usage=max_usage,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    reward_calls=reward_calls,
                )
            
            logger.info(f"Campaign code created successfully: {code.code}")
            return code

        except IntegrityError as e:
            # Handle duplicate code violation
            if 'duplicate key value violates unique constraint' in str(e) and 'code' in str(e):
                existing_code = code_data.get('code', final_code)
                logger.warning(f"Duplicate referral code attempted: {existing_code}")
                raise ConflictException(  # Better than ValidationException for conflicts
                    detail="Campaign code already exists",
                    context={
                        'code': existing_code,
                        'suggestion': 'Try a different code or let the system generate one automatically'
                    }
                )
            
            # Handle other integrity constraint violations
            logger.error(f"Database integrity error creating campaign code: {str(e)}")
            raise ConflictException(
                detail="Campaign code creation conflict",
                context={'reason': 'Database constraint violation'}
            )

        except ValidationException:
            raise  # Re-raise validation errors
        except DatabaseError as e:
            logger.error(f"Database error creating campaign code: {str(e)}")
            raise ServiceUnavailableException(
                detail="Campaign code database temporarily unavailable",
                context={'operation': 'create_campaign_code'}
            )
        except Exception as e:
            logger.error(f"Unexpected error creating campaign code: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Campaign code creation service temporarily unavailable",
                context={
                    'operation': 'create_campaign_code',
                    'user_message': 'Unable to create campaign code. Please try again.'
                }
            )
    
    @classmethod
    def get_active_campaigns(cls):
        """Get all active campaign codes"""
        ReferralCode = cls.get_referral_code_model()
        
        try:
            codes = ReferralCode.objects.filter(code_type='campaign')
            active_codes = [code for code in codes if code.is_valid]
            
            if not active_codes:
                logger.info("No active campaigns found")
                return []
            
            logger.debug(f"Found {len(active_codes)} active campaigns")
            return active_codes
            
        except DatabaseError as e:
            logger.error(f"Database error retrieving active campaigns: {str(e)}")
            raise ServiceUnavailableException(
                detail="Campaign database temporarily unavailable",
                context={'operation': 'get_active_campaigns'}
            )
        except AttributeError as e:
            # Handle case where is_valid property might not be available
            logger.error(f"Model attribute error: {str(e)}")
            raise ServiceUnavailableException(
                detail="Campaign service configuration error",
                context={'error': 'Model validation method unavailable'}
            )
        except Exception as e:
            logger.error(f"Unexpected error retrieving active campaigns: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Campaign retrieval service temporarily unavailable",
                context={
                    'operation': 'get_active_campaigns',
                    'user_message': 'Unable to load campaigns. Please try again.'
                }
            )
    
    @classmethod
    def get_campaign_by_code(cls, code):
        """Get campaign by specific code"""
        if not code or not isinstance(code, str):
            raise ValidationException(
                detail="Invalid campaign code",
                context={'code': 'Campaign code must be a non-empty string'}
            )
        
        ReferralCode = cls.get_referral_code_model()
        
        try:
            campaign = ReferralCode.objects.get(
                code=code.strip().upper(),
                code_type='campaign'
            )
            
            if not campaign.is_valid:
                raise NotFoundException(
                    detail="Campaign code not active",
                    context={
                        'code': code,
                        'status': campaign.status,
                        'reason': 'Campaign is expired or inactive'
                    }
                )
            
            return campaign
            
        except ReferralCode.DoesNotExist:
            raise NotFoundException(
                detail="Campaign code not found",
                context={'code': f"No campaign found with code: {code}"}
            )
        except DatabaseError as e:
            logger.error(f"Database error retrieving campaign {code}: {str(e)}")
            raise ServiceUnavailableException(
                detail="Campaign lookup database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Unexpected error retrieving campaign {code}: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Campaign lookup service temporarily unavailable"
            )
    
    @classmethod
    def validate_campaign_data(cls, code_data):
        """Validate campaign data before creation"""
        errors = {}
        
        # Validate required fields if custom validation needed
        if 'reward_calls' in code_data:
            try:
                reward = Decimal(str(code_data['reward_calls']))
                if reward < 0:
                    errors['reward_calls'] = 'Must be non-negative'
            except (InvalidOperation, ValueError):
                errors['reward_calls'] = 'Must be a valid number'
        
        if 'max_usage' in code_data:
            if not isinstance(code_data['max_usage'], int) or code_data['max_usage'] < 0:
                errors['max_usage'] = 'Must be a non-negative integer'
        
        if errors:
            raise ValidationException(
                detail="Campaign validation failed",
                context=errors
            )
        
        return True
