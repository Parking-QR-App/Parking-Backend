from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import BlacklistedAccessToken

class BlockBlacklistedTokensMiddleware(MiddlewareMixin):
    def process_request(self, request):
        auth = JWTAuthentication()
        header = auth.get_header(request)
        
        if header:
            try:
                token = auth.get_raw_token(header).decode("utf-8")  # Convert bytes to string
                if BlacklistedAccessToken.objects.filter(token=token).exists():
                    return JsonResponse({"error": "Token has been revoked", "status":401}, status=401)
            except Exception as e:
                return JsonResponse({"error": "Invalid token format", "status": 400}, status=400)

