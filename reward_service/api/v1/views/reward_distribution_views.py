from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from ..serializers.reward_distribution_serializer import ReferralCodeBatchCreateSerializer


class ReferralCodeBatchCreateView(APIView):
    permission_classes = [IsAdminUser]
    """
    Admin endpoint to bulk-create campaign-type referral codes (no underlying batch model).
    """
    def post(self, request):
        serializer = ReferralCodeBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(result, status=status.HTTP_201_CREATED)
