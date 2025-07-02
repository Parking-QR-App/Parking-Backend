from django.core.exceptions import ObjectDoesNotExist
from auth_service.models import UserDevice  # Direct model import

class AuthServiceClient:
    @staticmethod
    def get_user_device(user_id):
        """Get the most recently active device for a user"""
        try:
            return UserDevice.objects.filter(user_id=user_id).latest('last_active')
        except ObjectDoesNotExist:
            return None