from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404
from django.db import transaction
from decimal import Decimal

from ...models import ReferralCode, ReferralRelationship, ReferralSettings
from .serializers import (
    ReferralCodeSerializer, ReferralRelationshipSerializer,
    ReferralSettingsSerializer, CreateCampaignCodeSerializer
)
from ...services import ReferralService, CampaignService

# Import your API exceptions
from shared.utils.api_exceptions import (
    ValidationException, InvalidRequestException,
    ServiceUnavailableException
)

import logging
logger = logging.getLogger(__name__)

class UserReferralCodeView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get user's referral code"""
        try:
            code = ReferralService.get_user_referral_code(request.user)
            serializer = ReferralCodeSerializer(code)
            return Response({
                'message': 'User referral code retrieved successfully',
                'data': serializer.data,
                'status': status.HTTP_200_OK
            })
        except Exception as e:
            logger.error(f"Failed to get user referral code: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve referral code",
                context={'error': str(e)}
            )
    
    def post(self, request):
        """Create user's referral code (if doesn't exist)"""
        try:
            code = ReferralService.get_user_referral_code(request.user)
            serializer = ReferralCodeSerializer(code)

            return Response({
                'message': 'User referral code created successfully',
                'data': serializer.data,
                'status': status.HTTP_201_CREATED
            })
        except Exception as e:
            logger.error(f"Failed to create user referral code: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to create referral code",
                context={'error': str(e)}
            )

class DeactivateReferralCodeView(APIView):
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        try:
            code_id = request.data.get('code_id')
            if not code_id:
                raise InvalidRequestException(detail="code_id is required")
            
            code = get_object_or_404(ReferralCode, code=code_id)
            code.status = 'inactive'
            code.save()
            
            return Response({
                'message': 'Referral code deactivated successfully',
                'data': {'code_id': str(code_id)},
                'status': status.HTTP_200_OK
            })
        except Exception as e:
            logger.error(f"Failed to deactivate referral code: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to deactivate referral code",
                context={'error': str(e)}
            )

class CreateCampaignCodeView(APIView):
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        try:
            serializer = CreateCampaignCodeSerializer(data=request.data)
            if not serializer.is_valid():
                raise ValidationException(
                    detail="Invalid campaign code data",
                    context=serializer.errors
                )
            
            # Validate reward calls
            reward_calls = Decimal(str(serializer.validated_data.get('reward_calls', 0)))
            if reward_calls < Decimal('0.00'):
                raise ValidationException(
                    detail="Reward calls cannot be negative",
                    context={'reward_calls': 'Must be positive or zero'}
                )
            
            code = CampaignService.create_campaign_code(serializer.validated_data)
            return Response({
                'message': 'Campaign code created successfully',
                'data': ReferralCodeSerializer(code).data,
                'status': status.HTTP_201_CREATED
            })
        except ValidationException:
            raise
        except Exception as e:
            logger.error(f"Failed to create campaign code: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to create campaign code",
                context={'error': str(e)}
            )

class ReferralCodeDetailView(generics.RetrieveAPIView):
    """
    Retrieve details of a single referral code by its `id`.
    Only admins are allowed to access this endpoint.
    """
    permission_classes = [IsAdminUser]
    serializer_class = ReferralCodeSerializer
    queryset = ReferralCode.objects.all()
    lookup_field = "id"   # 👈 explicitly use model's `id` instead of `pk`

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(
                {
                    "message": "Referral code details retrieved successfully",
                    "data": serializer.data,
                    "status": status.HTTP_200_OK,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error(f"Failed to retrieve referral code: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve referral code",
                context={"error": str(e)},
            )
        

class ReferralRelationshipDetailView(generics.RetrieveAPIView):
    """
    Retrieve details of a referral relationship by its `id`.
    Only admins are allowed to access this endpoint.
    """
    permission_classes = [IsAdminUser]
    serializer_class = ReferralRelationshipSerializer
    queryset = ReferralRelationship.objects.all()
    lookup_field = "id"   # 👈 model field to match
    lookup_url_kwarg = "relationship_id"  # 👈 URL kwarg name

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            return Response(
                {
                    "message": "Referral relationship details retrieved successfully",
                    "data": serializer.data,
                    "status": status.HTTP_200_OK,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error(f"Failed to retrieve referral relationship: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve referral relationship",
                context={"error": str(e)},
            )

class UserReferralListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ReferralRelationshipSerializer
    
    def get_queryset(self):
        return ReferralRelationship.objects.filter(referrer=self.request.user)
    
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response({
                'message': 'User referrals retrieved successfully',
                'data': serializer.data,
                'status': status.HTTP_200_OK
            })
        except Exception as e:
            logger.error(f"Failed to retrieve user referrals: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve user referrals",
                context={'error': str(e)}
            )

class RegisterWithReferralView(APIView):
    permission_classes = []

    @transaction.atomic
    def post(self, request):
        from auth_service.services.registration_service import RegistrationService

        try:
            # 1. Extract referral/campaign code
            referral_code_str = request.data.get("referral_code")
            if not referral_code_str:
                raise InvalidRequestException(detail="Referral or campaign code is required")

            # 2. Validate code (try referral first, then campaign)
            code, error = ReferralService.validate_referral_code(referral_code_str)
            if error:
                try:
                    code = CampaignService.get_active_campaigns().get(code=referral_code_str)
                except ReferralCode.DoesNotExist:
                    raise InvalidRequestException(detail="Invalid or expired user/campaign code")

            # 3. Store code in session for OTP verification later
            if hasattr(request, "session"):
                request.session["pending_referral_code"] = referral_code_str
                if code.code_type == "user" and code.owner:
                    request.session["pending_referrer_id"] = str(code.owner.id)
                else:
                    request.session["pending_referrer_id"] = None
                request.session["pending_code_type"] = code.code_type
                request.session.save()
            else:
                logger.warning("Session not available for storing referral data")

            # 4. Register user
            email = request.data.get("email")
            if not email:
                raise InvalidRequestException(detail="Email is required for registration")

            try:
                user, created = RegistrationService.register_user(email.lower())
            except Exception as e:
                # cleanup session if registration fails
                if hasattr(request, "session"):
                    request.session.pop("pending_referral_code", None)
                    request.session.pop("pending_referrer_id", None)
                    request.session.pop("pending_code_type", None)
                    request.session.save()
                logger.error(f"User registration failed in referral flow: {str(e)}")
                raise ServiceUnavailableException(
                    detail="Failed to process referral registration",
                    context={"error": str(e)},
                    code="registration_failed",
                )

            response_data = {
                "email": user.email,
                "message": "OTP sent to email. Please verify.",
                "status": status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            }

            # 5. Immediate referral processing if user already verified
            try:
                if user.email_verified:
     
                    relationship = ReferralService.create_referral_relationship(
                        code.owner if code.code_type == "user" else None, 
                        user, 
                        code
                    )

                    completed_relationship = ReferralService.complete_referral(relationship)

                    response_data["referral"] = {
                        "code_used": code.code,
                        "code_type": code.code_type,
                        "reward_given": float(completed_relationship.reward_calls_given),
                        "processed": "immediately",
                    }
            
                    # clear session
                    if hasattr(request, "session"):
                        request.session.pop("pending_referral_code", None)
                        request.session.pop("pending_referrer_id", None)
                        request.session.pop("pending_code_type", None)
                        request.session.save()
            except Exception as e:
                logger.error(f"Referral/campaign immediate processing failed: {str(e)}")
                # not blocking, can retry later

            return Response(response_data, status=response_data["status"])

        except Exception as e:
            logger.error(f"Failed to process referral/campaign registration: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to process referral/campaign registration",
                context={"error": str(e)},
            )


class ReferralSettingsView(APIView):
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        try:
            settings = ReferralSettings.objects.all()
            serializer = ReferralSettingsSerializer(settings, many=True)
            return Response({
                'message': 'Referral settings retrieved successfully',
                'data': serializer.data,
                'status': status.HTTP_200_OK
            })
        except Exception as e:
            logger.error(f"Failed to retrieve referral settings: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve referral settings",
                context={'error': str(e)}
            )
    
    def post(self, request):
        try:
            key = request.data.get('key')
            value = request.data.get('value')
            description = request.data.get('description', '')
            
            if not key or not value:
                raise InvalidRequestException(detail="Key and value are required")
            
            setting = ReferralService.set_referral_settings(key, value, description)
            return Response({
                'message': 'Referral setting updated successfully',
                'data': ReferralSettingsSerializer(setting).data,
                'status': status.HTTP_200_OK
            })
        except Exception as e:
            logger.error(f"Failed to update referral setting: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to update referral setting",
                context={'error': str(e)}
            )

class CampaignCodeListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ReferralCodeSerializer
    queryset = ReferralCode.objects.filter(code_type='campaign')
    
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)
            return Response({
                'message': 'Campaign codes retrieved successfully',
                'data': serializer.data,
                'status': status.HTTP_200_OK
            })
        except Exception as e:
            logger.error(f"Failed to retrieve campaign codes: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve campaign codes",
                context={'error': str(e)}
            )
        

class UserReferralStatsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get user's referral statistics"""
        try:
            stats = ReferralService.get_user_referral_stats(request.user)
            return Response({
                'message': 'User referral statistics retrieved successfully',
                'data': stats,
                'status': status.HTTP_200_OK
            })
        except Exception as e:
            logger.error(f"Failed to get user referral stats: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve referral statistics",
                context={'error': str(e)}
            )