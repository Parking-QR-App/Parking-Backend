from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from django.shortcuts import get_object_or_404
from django.db import transaction
from decimal import Decimal
from django.db import DatabaseError, IntegrityError
from django.core.exceptions import ValidationError
from referral_service.services.import_service import ReferralServiceLoader
from referral_service.services.model_import_service import ReferralModelService
from auth_service.services.import_service import RegistrationServiceLoader
from ...models import ReferralCode, ReferralRelationship, ReferralSettings
from .serializers import (
    ReferralCodeSerializer, ReferralRelationshipSerializer,
    ReferralSettingsSerializer, CreateCampaignCodeSerializer
)
from ...services.referral_service import ReferralService
from ...services.campaign_service import CampaignService

# Import your API exceptions
from shared.utils.api_exceptions import (
    ValidationException, InvalidRequestException,
    ServiceUnavailableException, NotFoundException, ConflictException
)

import logging
logger = logging.getLogger(__name__)

class UserReferralCodeView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get user's referral code"""
        ReferralService = ReferralServiceLoader.get_referral_service()
        
        try:
            code = ReferralService.get_user_referral_code(request.user)
            
            if not code:
                raise NotFoundException(  # 404 - User doesn't have a referral code
                    detail="Referral code not found",
                    context={'user_id': str(request.user.id)}
                )
            
            serializer = ReferralCodeSerializer(code)
            return Response({
                'message': 'User referral code retrieved successfully',
                'data': serializer.data,
                'status': status.HTTP_200_OK
            })
            
        except NotFoundException:
            raise  # Re-raise
        except DatabaseError as e:
            logger.error(f"Database error retrieving referral code: {str(e)}")
            raise ServiceUnavailableException(
                detail="Database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to get user referral code: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Referral code service temporarily unavailable",
                context={'user_message': 'Unable to load referral code. Please try again.'}
            )
    
    def post(self, request):
        """Create user's referral code (if doesn't exist)"""
        ReferralService = ReferralServiceLoader.get_referral_service()

        try:
            # Check if user already has a referral code
            existing_code = ReferralService.get_user_referral_code(request.user)
            if existing_code:
                serializer = ReferralCodeSerializer(existing_code)
                return Response({
                    'message': 'User referral code already exists',
                    'data': serializer.data,
                    'status': status.HTTP_200_OK
                }, status=status.HTTP_200_OK)

            # Create new referral code
            code = ReferralService.create_user_referral_code(request.user)
            serializer = ReferralCodeSerializer(code)

            return Response({
                'message': 'User referral code created successfully',
                'data': serializer.data,
                'status': status.HTTP_201_CREATED
            }, status=status.HTTP_201_CREATED)
            
        except ValidationError as ve:
            raise ValidationException(  # 400 - Validation error
                detail="Referral code creation validation failed",
                context={'validation': str(ve)}
            )
        except IntegrityError:
            raise ConflictException(  # 409 - Code generation conflict
                detail="Referral code creation conflict",
                context={'reason': 'Unique code generation conflict'}
            )
        except Exception as e:
            logger.error(f"Failed to create user referral code: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Referral code creation service temporarily unavailable",
                context={'user_message': 'Unable to create referral code. Please try again.'}
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
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        ReferralCode = ReferralModelService.get_referral_code_model()
        RegistrationService = RegistrationServiceLoader.get_referral_service()
        ReferralService = ReferralServiceLoader.get_referral_service()
        CampaignService = ReferralServiceLoader.get_campaign_service()

        try:
            # 1. Validate required fields
            referral_code_str = request.data.get("referral_code")
            email = request.data.get("email")
            
            if not referral_code_str:
                raise ValidationException(  # 400 - Input validation
                    detail="Missing referral code",
                    context={'referral_code': 'Referral or campaign code is required'}
                )
            
            if not email:
                raise ValidationException(  # 400 - Input validation
                    detail="Missing email address",
                    context={'email': 'Email is required for registration'}
                )

            # 2. Validate and find referral/campaign code
            code = None
            code_error = None
            
            # Try referral code first
            try:
                code, error = ReferralService.validate_referral_code(referral_code_str)
                if error:
                    code_error = error
            except Exception as e:
                code_error = str(e)
            
            # If referral code failed, try campaign code
            if not code:
                try:
                    active_campaigns = CampaignService.get_active_campaigns()
                    code = active_campaigns.filter(code=referral_code_str).first()
                except Exception as e:
                    logger.warning(f"Campaign code lookup failed: {str(e)}")
            
            if not code:
                raise ValidationException(  # 400 - Invalid code
                    detail="Invalid referral code",
                    context={
                        'referral_code': f"'{referral_code_str}' is not a valid or active referral/campaign code",
                        'error_details': code_error
                    }
                )

            # 3. Store code in session for OTP verification
            self._store_referral_session_data(request, referral_code_str, code)

            # 4. Register user
            try:
                user, created = RegistrationService.register_user(email.lower().strip())
            except ValidationError as ve:
                self._cleanup_session(request)
                raise ValidationException(
                    detail="Registration validation failed",
                    context={'email': str(ve)}
                )
            except IntegrityError:
                self._cleanup_session(request)
                raise ConflictException(  # 409 - User already exists
                    detail="User already exists",
                    context={'email': 'This email is already registered'}
                )
            except Exception as e:
                self._cleanup_session(request)
                logger.error(f"User registration failed in referral flow: {str(e)}", exc_info=True)
                raise ServiceUnavailableException(  # 503 - Service issue
                    detail="Registration service temporarily unavailable",
                    context={'user_message': 'Unable to complete registration. Please try again.'}
                )

            response_data = {
                "data": {"email": user.email},
                "message": "Registration successful. OTP sent to email.",
                "status": status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            }

            # 5. Immediate referral processing if user already verified
            if user.email_verified:
                try:
                    relationship = ReferralService.create_referral_relationship(
                        code.owner if code.code_type == "user" else None,
                        user,
                        code
                    )

                    completed_relationship = ReferralService.complete_referral(relationship)

                    response_data["data"]["referral"] = {
                        "code_used": code.code,
                        "code_type": code.code_type,
                        "reward_given": float(completed_relationship.reward_calls_given),
                        "processed": "immediately",
                    }

                    self._cleanup_session(request)
                    
                except ValidationError as ve:
                    logger.error(f"Referral relationship validation failed: {str(ve)}")
                    # Don't fail registration, referral can be processed later
                except ConflictException as ce:
                    logger.warning(f"Referral relationship conflict: {str(ce)}")
                    # User might already have a referral relationship
                except Exception as e:
                    logger.error(f"Referral processing failed: {str(e)}", exc_info=True)
                    # Don't fail registration, referral can be processed later

            return Response(response_data, status=response_data["status"])

        except ValidationException:
            raise  # Re-raise validation errors
        except ConflictException:
            raise  # Re-raise conflict errors
        except ServiceUnavailableException:
            raise  # Re-raise service errors
        except Exception as e:
            logger.error(f"Referral registration failed: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Referral registration service temporarily unavailable",
                context={'user_message': 'Unable to complete referral registration. Please try again.'}
            )

    def _store_referral_session_data(self, request, referral_code_str, code):
        """Store referral data in session"""
        if not hasattr(request, "session"):
            logger.warning("Session not available for storing referral data")
            return
            
        try:
            request.session["pending_referral_code"] = referral_code_str
            if code.code_type == "user" and code.owner:
                request.session["pending_referrer_id"] = str(code.owner.id)
            else:
                request.session["pending_referrer_id"] = None
            request.session["pending_code_type"] = code.code_type
            request.session.save()
        except Exception as e:
            logger.warning(f"Failed to store referral session data: {str(e)}")

    def _cleanup_session(self, request):
        """Clean up referral session data"""
        if not hasattr(request, "session"):
            return
            
        try:
            request.session.pop("pending_referral_code", None)
            request.session.pop("pending_referrer_id", None)
            request.session.pop("pending_code_type", None)
            request.session.save()
        except Exception as e:
            logger.warning(f"Failed to cleanup referral session data: {str(e)}")


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