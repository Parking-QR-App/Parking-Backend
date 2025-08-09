# auth_service/throttles.py
from rest_framework.throttling import UserRateThrottle

class AuthThrottle(UserRateThrottle):
    scope = 'auth'  # Matches the 'auth' rate in settings
    
    def get_cache_key(self, request, view):
        # Throttle based on phone number in OTP requests
        if 'phone_number' in request.data:
            return f'auth_throttle:{request.data["phone_number"]}'
        return super().get_cache_key(request, view)