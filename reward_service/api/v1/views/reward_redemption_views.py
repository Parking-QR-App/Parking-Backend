from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404

from ..serializers import (
    ReferralCodeSerializer,
    UserReferralCodeCreateSerializer,
    CreateCampaignCodeSerializer
)
from ....models import ReferralCode, ReferralLimit
from ....services.exceptions import CodeValidationError
from utils.response_structure import success_response, error_response


class UserReferralCodeView(APIView):
    """
    Endpoint for user to get/create their personal referral code if eligible.
    POST with user_id returns the code if eligible, or error if not.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # enforce that user_id in payload matches requester unless staff
        user_id = request.data.get("user_id")
        if not user_id:
            return error_response("Missing user_id", {"user_id": "This field is required"}, status=status.HTTP_400_BAD_REQUEST)

        if str(request.user.user_id) != str(user_id) and not request.user.is_staff:
            return error_response("Forbidden", {"detail": "Cannot create referral code for another user"}, status=status.HTTP_403_FORBIDDEN)

        # Ensure referral limit exists for the user now that they're about to get a code
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(user_id=user_id)
        except User.DoesNotExist:
            return error_response("User not found", {"user_id": "No such user"}, status=status.HTTP_404_NOT_FOUND)

        ReferralLimit.objects.get_or_create(user=user)
        
        serializer = UserReferralCodeCreateSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
            result = serializer.save()
            return success_response("Referral code fetched/created", result, status=status.HTTP_200_OK)
        except Exception as e:
            # If it's a validation error from serializer it will be handled; catch any unexpected
            return error_response("Failed to get/create referral code", getattr(e, 'detail', str(e)), status=status.HTTP_400_BAD_REQUEST)


class CreateCampaignCodeView(APIView):
    """
    Admin endpoint to create a single campaign-type referral code.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = CreateCampaignCodeSerializer(data=request.data, context={'request': request})
        try:
            serializer.is_valid(raise_exception=True)
            result = serializer.save()
            return success_response("Campaign code created", result, status=status.HTTP_201_CREATED)
        except CodeValidationError as e:
            return error_response("Invalid campaign code request", {'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return error_response("Failed to create campaign code", getattr(e, 'detail', str(e)), status=status.HTTP_400_BAD_REQUEST)


class ReferralCodeDetailView(APIView):
    """
    Retrieve a referral code's details (read-only).
    """
    permission_classes = [IsAdminUser]

    def get(self, request, code_id):
        code_obj = get_object_or_404(ReferralCode, id=code_id)
        serializer = ReferralCodeSerializer(code_obj)
        return success_response("Referral code details fetched", serializer.data, status=status.HTTP_200_OK)

class DeactivateReferralCodeView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        code = get_object_or_404(ReferralCode, code=request.data.get('code_id'))
        code.status = 'inactive'
        code.save(update_fields=['status', 'updated_at'])
        return success_response("Referral code deactivated successfully")
