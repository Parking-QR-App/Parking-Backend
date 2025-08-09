from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ....models import ReferralLimit
from ..serializers.config_update_serializer import ReferralLimitSerializer
from rest_framework.permissions import IsAdminUser

class ReferralLimitDetailView(APIView):
    permission_classes = [IsAdminUser]
    """
    View a user's referral limit status and usage.
    """
    def get(self, request, user_id):
        try:
            limit = ReferralLimit.objects.get(user__id=user_id)
        except ReferralLimit.DoesNotExist:
            return Response({'detail': 'Referral limit not configured for user'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ReferralLimitSerializer(limit)
        return Response(serializer.data, status=status.HTTP_200_OK)
