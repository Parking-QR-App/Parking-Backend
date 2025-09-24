from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from auth_service.services.model_import_service import AuthService
from shared.utils.api_exceptions import (
    ValidationException,
    NotFoundException,
    ServiceUnavailableException
)
import logging

logger = logging.getLogger(__name__)

class AuthServiceClient:
    @staticmethod
    def get_user_device(user_id):
        """Get the most recently active device for a user"""
        if not user_id:
            raise ValidationException(
                detail="User ID is required",
                context={'user_id': 'User ID cannot be empty'}
            )
        
        try:
            UserDevice = AuthService.get_user_device_model()
            return UserDevice.objects.filter(user_id=user_id).latest('last_active')
            
        except ObjectDoesNotExist:
            raise NotFoundException(
                detail="User device not found",
                context={'user_id': str(user_id)}
            )
        except DatabaseError as e:
            logger.error(f"Database error getting user device: {str(e)}")
            raise ServiceUnavailableException(
                detail="User device database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Unexpected error getting user device: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="User device service temporarily unavailable"
            )
