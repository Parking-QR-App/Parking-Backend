from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from ....services.register_with_referral_service import RegisterWithReferralService
from rest_framework.permissions import AllowAny

class RegisterWithReferralView(APIView):
    permission_classes = [AllowAny]  # allow any or layer auth per your app

    @transaction.atomic
    def post(self, request):
        """
        Combined registration + referral application flow.
        Expects at least phone_number and required fields for auth_service.RegisterView plus optional referral_code.
        """
        service = RegisterWithReferralService()
        result = service.register(request)

        auth_response = result.get('auth_response')
        referral_relationship = result.get('referral_relationship')
        referral_error = result.get('referral_error')

        if auth_response is None or not hasattr(auth_response, 'status_code'):
            return Response({
                "message": "Registration failed",
                "errors": {
                    "referral_code": request.data.get("referral_code"),
                    "message": referral_error or "Authentication service error",
                },
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Prepare response payload
        response_payload = {
            'user': getattr(auth_response, 'data', None),
        }

        if referral_relationship:
            from ..serializers import ReferralRelationshipSerializer
            response_payload['referral_relationship'] = ReferralRelationshipSerializer(referral_relationship).data

        if referral_error:
            response_payload['referral_error'] = referral_error

        return Response({
            "data": response_payload,
            "message": "Registration completed successfully",
            "status": status.HTTP_201_CREATED
        }, status=status.HTTP_201_CREATED if auth_response.status_code == 201 else auth_response.status_code)
