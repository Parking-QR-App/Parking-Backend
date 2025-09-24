# auth_service/services/registration_service.py
import random
import logging
from django.utils import timezone
from django.apps import apps
from django.db import IntegrityError, DatabaseError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email

from ..utils import send_otp_email
from .firestore_service import create_user_in_firestore
from ..utils import generate_otp

# Import proper API exceptions
from shared.utils.api_exceptions import (
    ValidationException,
    ConflictException,
    ServiceUnavailableException,
)

logger = logging.getLogger(__name__)

class RegistrationService:

    _user_model = None

    @classmethod
    def get_user_model(cls):
        if cls._user_model is None:
            cls._user_model = apps.get_model('auth_service', 'User')
        return cls._user_model
    
    @classmethod
    def register_user(cls, email: str):
        """
        Register user - only for regular users
        Admin users are registered via AdminRegisterView
        """
        # Input validation
        if not email:
            raise ValidationException(
                detail="Email is required",
                context={'email': 'Email address cannot be empty'}
            )
        
        if not isinstance(email, str):
            raise ValidationException(
                detail="Invalid email format",
                context={'email': 'Email must be a string'}
            )
        
        # Validate email format
        email = email.strip().lower()
        try:
            validate_email(email)
        except DjangoValidationError:
            raise ValidationException(
                detail="Invalid email format",
                context={'email': f'"{email}" is not a valid email address'}
            )
        
        User = cls.get_user_model()
        
        try:
            # Generate OTP
            otp = generate_otp()
            if not otp:
                raise ServiceUnavailableException(
                    detail="OTP generation failed",
                    context={'service': 'OTP generation service unavailable'}
                )
            
            # Check if user already exists
            try:
                user = User.objects.get(email=email)
                # User exists - update OTP
                user.email_otp = otp
                user.email_otp_expiry = timezone.now() + timezone.timedelta(minutes=10)
                
                try:
                    user.save()
                    user_created = False
                    logger.info(f"Updated OTP for existing user: {email}")
                except DatabaseError as e:
                    logger.error(f"Database error updating user OTP: {str(e)}")
                    raise ServiceUnavailableException(
                        detail="User update database temporarily unavailable"
                    )
                    
            except User.DoesNotExist:
                # User doesn't exist - create new user
                user_created = True
                
                # Create user in Firestore first
                try:
                    firebase_user_profile = create_user_in_firestore(email)
                    if not firebase_user_profile:
                        raise ServiceUnavailableException(
                            detail="User profile creation failed",
                            context={'service': 'Firebase user profile creation failed'}
                        )
                        
                except Exception as e:
                    logger.error(f"Firestore user creation failed for {email}: {str(e)}")
                    raise ServiceUnavailableException(
                        detail="User profile service temporarily unavailable",
                        context={
                            'service': 'Firebase',
                            'user_message': 'Unable to create user profile. Please try again.'
                        }
                    )
                
                # Extract user data from Firebase with fallbacks
                user_id = firebase_user_profile.get('uid')
                if not user_id:
                    user_id = f"user_{random.randint(1000000000, 9999999999)}"
                    logger.warning(f"Generated fallback user_id for {email}: {user_id}")
                
                user_name = firebase_user_profile.get('username')
                if not user_name:
                    user_name = email.split('@')[0]
                    logger.info(f"Generated fallback username for {email}: {user_name}")
                
                # Create Django user
                try:
                    user = User.objects.create(
                        email=email,
                        email_otp=otp,
                        email_otp_expiry=timezone.now() + timezone.timedelta(minutes=10),
                        user_id=user_id,
                        user_name=user_name
                    )
                    logger.info(f"Created new user: {email}")
                    
                except IntegrityError as e:
                    logger.error(f"Integrity error creating user {email}: {str(e)}")
                    # Check if it's a duplicate user_id or email
                    if 'user_id' in str(e).lower():
                        raise ConflictException(
                            detail="User ID conflict",
                            context={
                                'user_id': 'Generated user ID already exists',
                                'suggestion': 'Please try registration again'
                            }
                        )
                    elif 'email' in str(e).lower():
                        raise ConflictException(
                            detail="Email already registered",
                            context={
                                'email': f'User with email {email} already exists',
                                'suggestion': 'Try logging in instead'
                            }
                        )
                    else:
                        raise ConflictException(
                            detail="User registration conflict",
                            context={'reason': 'Database constraint violation'}
                        )
                        
                except DatabaseError as e:
                    logger.error(f"Database error creating user {email}: {str(e)}")
                    raise ServiceUnavailableException(
                        detail="User registration database temporarily unavailable"
                    )

            # Send OTP email
            try:
                # Use async task for email sending
                send_otp_email(email, otp, user.user_name)
                logger.info(f"OTP email queued for {email}")
                
            except Exception as e:
                logger.error(f"Failed to queue OTP email for {email}: {str(e)}")
                # Don't fail registration for email issues, but log the problem
                logger.warning(f"Registration completed but OTP email failed for {email}")
        
            return user, user_created
        
        except ValidationException:
            raise  # Re-raise validation errors
        except ConflictException:
            raise  # Re-raise conflict errors
        except ServiceUnavailableException:
            raise  # Re-raise service errors
        except Exception as e:
            logger.error(f"Unexpected error during registration for {email}: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Registration service temporarily unavailable",
                context={
                    'user_message': 'Unable to complete registration. Please try again.',
                    'email': email
                }
            )
