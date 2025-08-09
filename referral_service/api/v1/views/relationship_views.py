from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated, IsAdminUser

from ..serializers.relationship_serializer import (
    ApplyReferralCodeSerializer,
    ReferralRelationshipSerializer
)

from ....services.referral_relationship_service import ReferralRelationshipService
from ....services.exceptions import RelationshipError, CodeValidationError
from ....models import ReferralRelationship
from utils.response_structure import success_response, error_response
from django.contrib.auth import get_user_model

User = get_user_model()


class ApplyReferralCodeView(APIView):
    permission_classes = [IsAuthenticated]  # ensure user is applying for themselves or admin

    def post(self, request):
        serializer = ApplyReferralCodeSerializer(
            data=request.data,
            context={'request_meta': request.META}
        )
        serializer.is_valid(raise_exception=True)
        referral_code = serializer.validated_data['referral_code']
        referred_user = serializer.context['referred_user']
        request_meta = serializer.context.get('request_meta', {})

        # Enforce active code
        try:
            from ....services.referral_code_service import ReferralCodeService
            ReferralCodeService.get_active_code(referral_code)
        except CodeValidationError as e:
            return error_response("Invalid referral code", {'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        service = ReferralRelationshipService()
        try:
            relationship = service.register_with_code(referral_code, referred_user, request_meta)
        except RelationshipError as e:
            return error_response("Failed to apply referral code", {'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        output = ReferralRelationshipSerializer(relationship)
        return Response(success_response("Referral code applied", output.data), status=status.HTTP_201_CREATED)


class ReferralRelationshipDetailView(APIView):
    permission_classes = [IsAdminUser]
    """
    Fetch a particular referral relationship.
    """
    def get(self, request, relationship_id):
        rel = get_object_or_404(ReferralRelationship, id=relationship_id)
        serializer = ReferralRelationshipSerializer(rel)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UserReferralListView(APIView):
    permission_classes = [IsAdminUser]
    """
    List all referral relationships made by the authenticated user (as referrer)
    or received (as referred).
    """
    def get(self, request):
        user = request.user
        made_qs = user.referrals_made.all().order_by('-created_at')
        received = getattr(user, 'referral_source', None)
        from ..serializers.relationship_serializer import ReferralRelationshipSerializer

        made_serialized = ReferralRelationshipSerializer(made_qs, many=True).data
        received_serialized = ReferralRelationshipSerializer(received).data if received else None

        return Response({
            'made': made_serialized,
            'received': received_serialized
        }, status=status.HTTP_200_OK)
