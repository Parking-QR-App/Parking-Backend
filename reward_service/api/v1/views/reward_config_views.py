from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from ..serializers.reward_config_serializer import (
    AdminSetLimitsSerializer,
    AdminAdjustLimitsSerializer
)
from rest_framework.permissions import IsAdminUser


class AdminSetLimitsView(APIView):
    permission_classes = [IsAdminUser]
    """
    Admin endpoint to set absolute referral limits for a user.
    """
    def post(self, request):
        serializer = AdminSetLimitsSerializer(data=request.data, context={'actor': request.user})
        serializer.is_valid(raise_exception=True)
        try:
            limit = serializer.save()
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'Limits updated', 'limits': limit.id}, status=status.HTTP_200_OK)


class AdminAdjustLimitsView(APIView):
    permission_classes = [IsAdminUser]
    """
    Admin endpoint to incrementally adjust (delta) referral limits.
    """
    def post(self, request):
        serializer = AdminAdjustLimitsSerializer(data=request.data, context={'actor': request.user})
        serializer.is_valid(raise_exception=True)
        try:
            limit = serializer.save()
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'Limits adjusted', 'limits': limit.id}, status=status.HTTP_200_OK)
