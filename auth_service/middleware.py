from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import BlacklistedAccessToken, UserDevice
from django.utils.timezone import now
import logging
from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)

class BlockBlacklistedTokensMiddleware(MiddlewareMixin):
    """
    Enhanced with:
    - Better token validation
    - Caching for blacklist checks
    - Structured logging
    """
    def process_request(self, request):
        # Skip middleware for specific paths
        if request.path.startswith('/admin/') or request.path == '/healthcheck/':
            return None

        auth = JWTAuthentication()
        try:
            header = auth.get_header(request)
            if header is None:
                return None

            raw_token = auth.get_raw_token(header)
            if isinstance(raw_token, bytes):
                raw_token = raw_token.decode("utf-8")

            # Cache check for better performance
            cache_key = f"blacklisted_token:{raw_token}"
            if cache.get(cache_key):
                logger.warning(f"Blocked blacklisted token for {request.path}")
                return JsonResponse({
                    "message": "Token revoked",
                    "code": "token_blacklisted",
                    "status": 401
                }, status=401)

            # Database check with cache fallback
            if BlacklistedAccessToken.objects.filter(
                token=raw_token, 
                expires_at__gt=now()
            ).exists():
                cache.set(cache_key, True, timeout=3600)  # Cache for 1 hour
                return JsonResponse({
                    "message": "Token revoked",
                    "code": "token_blacklisted",
                    "status": 401
                }, status=401)

        except Exception as e:
            logger.error(f"Token validation failed: {str(e)}")
            return JsonResponse({
                "message": "Invalid token",
                "code": "token_invalid",
                "status": 400
            }, status=400)


class DeviceActivityMiddleware(MiddlewareMixin):
    """
    Improvements:
    - Atomic updates
    - Device existence verification
    - Rate-limited updates
    - Referral attribution support
    """
    def __call__(self, request):
        response = self.get_response(request)
        
        if not request.user.is_authenticated:
            return response

        device_id = request.headers.get("X-Device-ID")
        if not device_id:
            return response

        # Rate limit updates to once per 5 minutes per device
        cache_key = f"device_activity:{request.user.pk}:{device_id}"
        if cache.get(cache_key):
            return response

        update_data = {
            "last_active": now(),
            "ip_address": self._get_client_ip(request)
        }

        if fcm_token := request.headers.get("X-FCM-Token"):
            update_data["fcm_token"] = fcm_token

        try:
            with transaction.atomic():
                device, created = UserDevice.objects.update_or_create(
                    user=request.user,
                    device_id=device_id,
                    defaults=update_data
                )
                
                # If new device, check for referral attribution
                if created:
                    self._check_referral_attribution(device)

            cache.set(cache_key, True, timeout=300)  # 5 minute cooldown
            
        except Exception as e:
            logger.error(f"Device update failed: {str(e)}")

        return response

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

    def _check_referral_attribution(self, device):
        """Check if device has pending referral attribution"""
        from referral_service.utils.admin import get_attribution
        if attribution := get_attribution(device.device_id):
            logger.info(f"New device with referral attribution: {attribution}")