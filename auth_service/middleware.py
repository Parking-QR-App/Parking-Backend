from django.utils.timezone import now
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
import logging
from .models import BlacklistedAccessToken, UserDevice

logger = logging.getLogger(__name__)


class BlockBlacklistedTokensMiddleware(MiddlewareMixin):
    CACHE_PREFIX = "AUTH:BLACKLIST:TOKEN:"

    def process_request(self, request):
        excluded_paths = [
            '/admin/',
            '/healthcheck/',
            '/api/auth/register/',
            '/api/auth/send-email-otp/',
        ]
        if any(request.path.startswith(path) for path in excluded_paths):
            return None

        auth = JWTAuthentication()
        try:
            header = auth.get_header(request)
            if header is None:
                return None

            raw_token = auth.get_raw_token(header)
            if isinstance(raw_token, bytes):
                raw_token = raw_token.decode("utf-8")

            cache_key = f"{self.CACHE_PREFIX}{raw_token}"

            # Cache check
            if cache.get(cache_key):
                return JsonResponse(
                    {
                        "error": {
                            "message": "Token has been revoked",
                            "code": "token_blacklisted",
                            "status": 401,
                        }
                    },
                    status=401,
                )

            # DB check with fallback
            if BlacklistedAccessToken.objects.filter(
                token=raw_token,
                expires_at__gt=now(),
            ).exists():
                cache.set(cache_key, True, timeout=3600)
                return JsonResponse(
                    {
                        "error": {
                            "message": "Token has been revoked",
                            "code": "token_blacklisted",
                            "status": 401,
                        }
                    },
                    status=401,
                )

        except Exception as e:
            logger.error(f"Token validation failed: {str(e)}")
            return None  # Don’t block on middleware error


class DeviceActivityMiddleware(MiddlewareMixin):
    def __call__(self, request):
        response = self.get_response(request)

        if not request.user.is_authenticated:
            return response

        device_id = request.headers.get("X-Device-ID")
        if not device_id:
            return JsonResponse(
                {
                    "error": {
                        "message": "Device ID is required",
                        "code": "missing_device_id",
                        "status": 400,
                    }
                },
                status=400,
            )

        cache_key = f"DEVICE:ACTIVITY:{request.user.pk}:{device_id}"
        if cache.get(cache_key):
            return response

        update_data = {
            "last_active": now(),
            "ip_address": self._get_client_ip(request),
        }

        if fcm_token := request.headers.get("X-FCM-Token"):
            update_data["fcm_token"] = fcm_token
        else:
            return JsonResponse(
                {
                    "error": {
                        "message": "FCM Token is required",
                        "code": "missing_fcm_token",
                        "status": 400,
                    }
                },
                status=400,
            )

        try:
            with transaction.atomic():
                UserDevice.objects.update_or_create(
                    user=request.user,
                    device_id=device_id,
                    defaults=update_data,
                )
            cache.set(cache_key, True, timeout=300)

        except Exception as e:
            logger.error(f"Device update failed: {str(e)}")

        return response

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return (
            x_forwarded_for.split(',')[0]
            if x_forwarded_for
            else request.META.get('REMOTE_ADDR')
        )
