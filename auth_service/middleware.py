from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import BlacklistedAccessToken, UserDevice
from django.utils.timezone import now

class BlockBlacklistedTokensMiddleware(MiddlewareMixin):
    def process_request(self, request):
        auth = JWTAuthentication()
        header = auth.get_header(request)

        if not header:
            return  # No token passed; possibly a public route

        try:
            raw_token = auth.get_raw_token(header)
            if isinstance(raw_token, bytes):
                raw_token = raw_token.decode("utf-8")
            print("🛡️ BlockBlacklistedTokensMiddleware triggered")
            # Check if token is blacklisted
            if BlacklistedAccessToken.objects.filter(token=raw_token).exists():
                return JsonResponse({
                    "message": "Token has been revoked",
                    "errors": {"token": "Access token has been blacklisted"},
                    "status": 401
                }, status=401)

        except Exception:
            return JsonResponse({
                "message": "Invalid token format",
                "errors": {"token": "Unable to decode access token"},
                "status": 400
            }, status=400)


class DeviceActivityMiddleware(MiddlewareMixin):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated:
            device_id = request.headers.get("X-Device-ID")
            fcm_token = request.headers.get("X-FCM-Token")
            if not device_id:
                return response  # Cannot track activity without device_id

            update_fields = {"last_active": now()}

            if fcm_token:
                update_fields["fcm_token"] = fcm_token

            # Ensure device exists before update
            UserDevice.objects.filter(
                user=request.user,
                device_id=device_id
            ).update(**update_fields)

        return response
