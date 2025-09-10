from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenRefreshView
from django.utils.timezone import now
from .models import User, BlacklistedAccessToken, UserDevice

from shared.utils.api_exceptions import (
    InvalidRequestException, AuthenticationException, BaseServiceException, ValidationException
)

from .serializers import (
    RegisterSerializer, VerifyOTPSerializer, AdminUserSerializer,
    VerifyEmailOTPSerializer, EmailOTPSerializer, BlacklistedAccessTokenSerializer, BaseUserSerializer, FlexibleUpdateUserInfoSerializer
)
from .services.registration_service import RegistrationService
from .utils import send_otp_email, generate_otp
from rest_framework_simplejwt.tokens import RefreshToken
import random  # For generating the OTP
from django.utils import timezone
from auth_service.services.firestore_service import create_user_in_firestore
from django.db import transaction
from .throttles import AuthThrottle

import logging

logger = logging.getLogger(__name__)



class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        fcm_token = request.headers.get("X-FCM-Token")
        device_id = request.headers.get("X-Device-ID")
        refresh_token = request.data.get("refresh")

        if not fcm_token or not device_id:
            raise InvalidRequestException(
                detail="FCM-TOKEN and DEVICE-ID headers are required",
                context={'device': 'FCM-TOKEN and DEVICE-ID headers are required'}
            )

        if not refresh_token:
            raise InvalidRequestException(
                detail="Refresh token is required",
                context={'refresh': 'Refresh token is required'}
            )

        try:
            refresh = RefreshToken(refresh_token)
            user = refresh.user

            device = UserDevice.objects.filter(user=user, device_id=device_id, fcm_token=fcm_token).first()
            if not device:
                raise AuthenticationException(
                    detail="Device not recognized or unauthorized",
                    context={'device': 'Device not recognized or unauthorized'}
                )

            # Blacklist old access token
            if device.last_access_token:
                try:
                    BlacklistedAccessToken.objects.get_or_create(
                        token=device.last_access_token,
                        user=user
                    )
                except Exception:
                    pass

            # Blacklist the used refresh token
            try:
                refresh.blacklist()
            except Exception:
                pass

            new_refresh = RefreshToken.for_user(user)
            new_access = new_refresh.access_token

            # Update device
            device.last_refresh_token_jti = new_refresh['jti']
            device.last_access_token = str(new_access)
            device.last_active = now()
            device.save()

            return Response({
                'message': 'Token refreshed',
                'data': {
                    'access_token': str(new_access),
                    'refresh_token': str(new_refresh),
                },
                'status': status.HTTP_200_OK
            })

        except TokenError as e:
            raise AuthenticationException(
                detail="Invalid or expired refresh token",
                context={'token': 'Invalid or expired refresh token'}
            )


# auth_service/views.py
class RegisterView(APIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].lower()

        try:
            user, created = RegistrationService.register_user(email)
            return Response({
                'email': user.email,
                'message': 'OTP sent to email. Please verify.'
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Registration failed: {str(e)}")
            raise BaseServiceException(detail="Registration failed", context={'error': str(e)})


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    @transaction.atomic
    def post(self, request):
        """
        Verify OTP and complete user registration/login
        Handles both registration and login scenarios
        """
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            raise ValidationException(
                detail="Invalid OTP data",
                context=serializer.errors
            )

        user = serializer.validated_data["user"]
        device_type = serializer.validated_data.get("device_type", "web")
        os_version = serializer.validated_data.get("os_version", "")
        fcm_token = request.headers.get("X-FCM-Token")
        device_id = request.headers.get("X-Device-ID")

        if not fcm_token or not device_id:
            raise InvalidRequestException(
                detail="X-FCM-Token and X-Device-ID headers are required",
                context={'headers': 'X-FCM-Token and X-Device-ID headers are required'}
            )

        try:
            # Check if this is first login (registration) or subsequent login
            is_first_login = not user.email_verified
            user_created_recently = (timezone.now() - user.created_at).total_seconds() < 300  # Within 5 minutes

            # 1. Clean up old devices and tokens
            with transaction.atomic():
                self._cleanup_old_devices(user, device_id, fcm_token)
                
                # Save new device
                device, device_created = UserDevice.objects.update_or_create(
                    user=user,
                    device_id=device_id,
                    defaults={
                        'fcm_token': fcm_token,
                        'device_type': device_type,
                        'os_version': os_version,
                        'ip_address': self.get_client_ip(request),
                        'last_active': timezone.now()
                    }
                )
                
                # Generate tokens
                refresh = RefreshToken.for_user(user)
                access = refresh.access_token

                device.last_access_token = str(access)
                device.last_refresh_token_jti = refresh['jti']
                device.save()

                # Mark email as verified and clear OTP (only if not already verified)
                if not user.email_verified:
                    user.email_verified = True
                    user.email_otp = None
                    user.email_otp_expiry = None
                    user.save()

            # 2. Initialize call balance if first login
            if is_first_login:
                try:
                    from platform_settings.services import CallBalanceService
                    CallBalanceService.initialize_user_balance(user)
                    logger.info(f"Initialized call balance for user {user.user_id}")
                except Exception as e:
                    logger.error(f"Failed to initialize call balance for user {user.user_id}: {str(e)}")

            # 3. Process referral logic for new users
            referral_data = {}
            if is_first_login and hasattr(request, 'session'):
                referral_data = self._process_pending_referral(user, request)

            # 4. Send welcome email only for first-time registration
            if is_first_login and user_created_recently:
                try:
                    from .utils import send_welcome_email
                    send_welcome_email(user.email, user.get_full_name() or user.user_name)
                    logger.info(f"Welcome email sent to new user: {user.email}")
                except Exception as e:
                    logger.warning(f"Failed to send welcome email: {str(e)}")


            # 5. Fetch current balance
            from platform_settings.services import CallBalanceService
            current_balance = CallBalanceService.get_user_balance(user)

            # 6. Build response
            response_data = {
                'access_token': str(access),
                'refresh_token': str(refresh),
                'user_id': user.user_id,
                'user_name': user.user_name,
                'email': user.email,
                'first_name': user.first_name or "",
                'last_name': user.last_name or "",
                'email_verified': user.email_verified,
                'phone_verified': user.phone_verified,
                'active_devices': user.devices.count(),
                'has_profile': bool(user.first_name and user.last_name),
                'is_new_user': is_first_login,  # Indicate if this is a new user
                'call_balance': {
                    'base': str(current_balance.base_balance),
                    'bonus': str(current_balance.bonus_balance),
                    'total': str(current_balance.total_balance),
                },
                'referral_data': referral_data
            }

            return Response({
                'message': 'Registration successful' if is_first_login else 'Login successful',
                'data': response_data,
                'status': status.HTTP_200_OK
            })

        except ValidationException:
            raise
        except AuthenticationException:
            raise
        except Exception as e:
            logger.exception(f"Unexpected error during OTP verification: {str(e)}")
            raise BaseServiceException(
                detail="An unexpected error occurred during login",
                context={'system': 'Internal server error'}
            )

    def _process_pending_referral(self, user, request):
        """
        Process any pending referral or campaign code from session
        """
        from referral_service.models import ReferralCode
        referral_data = {}

        # Check if session exists and has the required keys
        if not hasattr(request, 'session'):
            return referral_data

        referral_code = request.session.get("pending_referral_code")
        referrer_id = request.session.get("pending_referrer_id")
        code_type = request.session.get("pending_code_type")
        print(referral_code, referrer_id, code_type)
        if referral_code and code_type:
            try:
                from referral_service.services import ReferralService, CampaignService

                if code_type == "user" and referrer_id:
                    # Handle normal referral
                    referrer = User.objects.get(id=referrer_id)
                    code, error = ReferralService.validate_referral_code(referral_code)
                    if error:
                        logger.warning(f"Invalid pending referral code {referral_code}: {error}")
                        return referral_data

                    relationship = ReferralService.create_referral_relationship(
                        referrer, user, code
                    )
                    completed_relationship = ReferralService.complete_referral(relationship)

                    referral_data = {
                        "was_referred": True,
                        "referrer_id": str(referrer.user_id),
                        "referrer_email": referrer.email,
                        "referral_code": code.code,
                        "reward_given": float(completed_relationship.reward_calls_given),
                        "relationship_id": str(relationship.id),
                        "processed": "during_verification",
                    }

                elif code_type == "campaign":
                    # Handle campaign code
                    try:
                        code = CampaignService.get_active_campaigns().get(code=referral_code)
                    except ReferralCode.DoesNotExist:
                        logger.warning(f"Invalid pending campaign code {referral_code}")
                        return referral_data

                    relationship = ReferralService.create_referral_relationship(
                        None, user, code
                    )
                    completed_relationship = ReferralService.complete_referral(relationship)

                    referral_data = {
                        "was_referred": True,
                        "referral_code": code.code,
                        "reward_given": float(completed_relationship.reward_calls_given),
                        "relationship_id": str(relationship.id),
                        "processed": "during_verification",
                        "campaign": True,
                    }

                logger.info(f"Pending {code_type} completed for user {user.user_id}")

                # clear session
                request.session.pop("pending_referral_code", None)
                request.session.pop("pending_referrer_id", None)
                request.session.pop("pending_code_type", None)
                request.session.save()

            except Exception as e:
                logger.error(f"Failed to process pending {code_type}: {str(e)}")
                referral_data = {
                    "was_referred": True,
                    "error": f"{code_type} processing failed",
                    "referral_code": referral_code,
                }

        return referral_data

    

    def _cleanup_old_devices(self, user, device_id, fcm_token):
        """Clean up old devices and blacklist tokens (existing logic)"""
        # Remove old device and blacklist tokens
        old_device = user.devices.first()
        if old_device:
            # Blacklist the old access token in your model
            if old_device.last_access_token:
                print(old_device.last_access_token)
                try:
                    BlacklistedAccessToken.objects.get_or_create(
                        token=old_device.last_access_token,
                        user=user
                    )
                except Exception:
                    pass

            # Blacklist refresh token (SimpleJWT built-in)
            if old_device.last_refresh_token_jti:
                from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
                BlacklistedToken.objects.filter(token__jti=old_device.last_refresh_token_jti).delete()
                OutstandingToken.objects.filter(jti=old_device.last_refresh_token_jti).delete()

            old_device.delete()
            
        UserDevice.objects.filter(device_id=device_id).delete()
        UserDevice.objects.filter(fcm_token=fcm_token).delete()

    # def _get_qr_info(self, user):
    #     """Get QR code info (existing logic preserved)"""
    #     qr_code = QRCode.objects.filter(user=user, is_active=True).first()
    #     if qr_code:
    #         return {
    #             "domain": settings.BACKEND_URL,
    #             "api_route": "/qr/scan-qr/",
    #             "hashed_qr_id": str(generate_qr_code(qr_code.qr_id, qr_code.created_at))
    #         }
    #     return ''

    def get_client_ip(self, request):
        """Get client IP (existing logic preserved)"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

    
# class VerifyOTPView(APIView):
#     permission_classes = [AllowAny]
#     # throttle_classes = [AuthThrottle]  # include if imported

#     @transaction.atomic
#     def post(self, request):
#         """
#         Verify OTP and complete user registration/login.
#         Enhancements: referral verification and registration reward triggering.
#         """
#         serializer = VerifyOTPSerializer(data=request.data)
#         if not serializer.is_valid():
#             return Response({
#                 'message': 'Error',
#                 'errors': serializer.errors,
#                 'status': status.HTTP_400_BAD_REQUEST
#             }, status=status.HTTP_400_BAD_REQUEST)

#         user = serializer.validated_data["user"]
#         device_type = serializer.validated_data.get("device_type", "")
#         fcm_token = request.headers.get("X-FCM-Token")
#         device_id = request.headers.get("X-Device-ID")

#         if not fcm_token or not device_id:
#             return Response({
#                 'message': 'Error',
#                 'errors': {'headers': 'FCM-TOKEN and DEVICE-ID headers are required'},
#                 'status': status.HTTP_400_BAD_REQUEST
#             }, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             # 1. Device / token management
#             with transaction.atomic():
#                 self._cleanup_old_devices(user, device_id, fcm_token)

#                 device, _ = UserDevice.objects.update_or_create(
#                     user=user,
#                     device_id=device_id,
#                     defaults={
#                         'fcm_token': fcm_token,
#                         'device_type': device_type,
#                         'os_version': serializer.validated_data.get("os_version", ""),
#                         'ip_address': self.get_client_ip(request),
#                         'last_active': timezone.now(),
#                     }
#                 )

#                 refresh = RefreshToken.for_user(user)
#                 access = refresh.access_token

#                 device.last_access_token = str(access)
#                 device.last_refresh_token_jti = refresh['jti']
#                 device.save()

#             # 2. Referral-related logic: verify pending relationship and grant registration reward
#             referral_payload = {}
#             try:
#                 relationship = ReferralRelationship.objects.select_for_update().filter(
#                     referred_user=user,
#                     status='pending'
#                 ).first()
#                 if relationship:
#                     now = timezone.now()
#                     # Mark email/OTP verified
#                     relationship.user_verified_at = now
#                     if relationship.created_at:
#                         delta = now - relationship.created_at
#                         relationship.days_to_verify = delta.days
#                     relationship.status = 'verified'
#                     relationship.save(update_fields=[
#                         'user_verified_at', 'days_to_verify', 'status', 'updated_at'
#                     ])

#                     # Log email verified event
#                     log_event(
#                         user=user,
#                         event_type=EVENT_TYPE_USER_VERIFIED,
#                         referral_relationship=relationship,
#                         referral_code=relationship.referral_code_used,
#                         metadata={'stage': 'otp_verified'},
#                         ip_address=self.get_client_ip(request),
#                         user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
#                         device_type=device_type or ''
#                     )

#                     # Attempt to grant registration reward if not already rewarded.
#                     # Hook into reward service if available.
#                     try:
#                         # Try importing a reward granter; adapt path if your reward service exposes differently.
#                         from reward_service.services import grant_reward  # expected signature below
#                     except ImportError:
#                         grant_reward = None

#                     if grant_reward:
#                         try:
#                             # grant_reward(referrer, referred_user, trigger_event, relationship, payment_amount=None)
#                             grant_reward(
#                                 referrer=relationship.referrer,
#                                 referred_user=user,
#                                 trigger_event='registration',
#                                 relationship=relationship
#                             )
#                             # Mark rewarded timestamps
#                             now2 = timezone.now()
#                             if not relationship.referrer_rewarded_at:
#                                 relationship.referrer_rewarded_at = now2
#                             if not relationship.referred_user_rewarded_at:
#                                 relationship.referred_user_rewarded_at = now2
#                             relationship.status = 'rewarded'
#                             relationship.save(update_fields=[
#                                 'referrer_rewarded_at', 'referred_user_rewarded_at', 'status', 'updated_at'
#                             ])

#                             log_event(
#                                 user=user,
#                                 event_type=EVENT_TYPE_REWARD_GIVEN,
#                                 referral_relationship=relationship,
#                                 referral_code=relationship.referral_code_used,
#                                 metadata={'for': 'registration'},
#                                 ip_address=self.get_client_ip(request),
#                                 user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
#                                 device_type=device_type or ''
#                             )
#                         except Exception as e:
#                             logger.warning("Failed to grant referral registration reward: %s", str(e))

#                     # Include referral relationship in response
#                     from referral_service.api.v1.serializers.relationship_serializer import ReferralRelationshipSerializer
#                     referral_payload['referral_relationship'] = ReferralRelationshipSerializer(relationship).data

#             except Exception as e:
#                 logger.exception("Referral verification path failed for user %s: %s", getattr(user, 'user_id', None), str(e))
#                 # proceed without blocking

#             # 3. QR info
#             qr_info = self._get_qr_info(user)

#             # 4. Build response
#             response_data = {
#                 'access_token': str(access),
#                 'refresh_token': str(refresh),
#                 'user_id': user.user_id,
#                 'user_name': user.user_name,
#                 'email': user.email if getattr(user, 'email_verified', False) else "",
#                 'first_name': user.first_name or "",
#                 'last_name': user.last_name or "",
#                 'active_devices': user.devices.count(),
#                 'qr': qr_info,
#             }
#             response_data.update(referral_payload)

#             return Response({
#                 'message': 'Login successful',
#                 'data': response_data,
#                 'status': status.HTTP_200_OK
#             }, status=status.HTTP_200_OK)

#         except Exception as e:
#             logger.exception(f"OTP verification failed for user {getattr(user, 'user_id', None)}: {str(e)}")
#             return Response({
#                 'message': 'Error',
#                 'errors': {'system': 'Login processing failed'},
#                 'status': status.HTTP_500_INTERNAL_SERVER_ERROR
#             }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#     def _cleanup_old_devices(self, user, device_id, fcm_token):
#         """Clean up old devices and blacklist tokens."""
#         # Remove oldest device if present
#         old_device = user.devices.first()
#         if old_device:
#             if old_device.last_access_token:
#                 try:
#                     BlacklistedAccessToken.objects.get_or_create(
#                         token=old_device.last_access_token,
#                         user=user
#                     )
#                 except Exception:
#                     pass

#             if old_device.last_refresh_token_jti:
#                 try:
#                     from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
#                     BlacklistedToken.objects.filter(token__jti=old_device.last_refresh_token_jti).delete()
#                     OutstandingToken.objects.filter(jti=old_device.last_refresh_token_jti).delete()
#                 except Exception:
#                     pass

#             old_device.delete()

#         UserDevice.objects.filter(device_id=device_id).delete()
#         UserDevice.objects.filter(fcm_token=fcm_token).delete()

#     def _get_qr_info(self, user):
#         """Get QR code info."""
#         qr_code = QRCode.objects.filter(user=user, is_active=True).first()
#         if qr_code:
#             return {
#                 "domain": settings.BACKEND_URL,
#                 "api_route": "/qr/scan-qr/",
#                 "hashed_qr_id": str(generate_qr_code(qr_code.qr_id, qr_code.created_at))
#             }
#         return ''

#     def get_client_ip(self, request):
#         """Get client IP (existing logic preserved)"""
#         x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
#         return x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            access_token = request.auth
            refresh_token = request.data.get("refresh_token")
            fcm_token = request.data.get("fcm_token")

            if access_token:
                BlacklistedAccessToken.objects.create(token=str(access_token))

            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()

            if fcm_token:
                UserDevice.objects.filter(user=request.user, fcm_token=fcm_token).delete()

            return Response({'message': "Logged out", "status": status.HTTP_205_RESET_CONTENT},
                            status=status.HTTP_205_RESET_CONTENT)

        except Exception:
            raise InvalidRequestException(detail="Invalid logout request")


class SendEmailOTPView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = EmailOTPSerializer(data=request.data, context={'request': request})

        if serializer.is_valid():
            email = serializer.validated_data['email']
            user = request.user

            if user.email and user.email == email and user.email_verified:
                return Response({
                    "data": None,
                    "message": "Email already verified.",
                    "status": status.HTTP_200_OK
                }, status=status.HTTP_200_OK)

            otp = generate_otp()
            user.email = email
            user.email_otp = otp
            user.email_otp_expiry = timezone.now() + timezone.timedelta(minutes=10)
            user.save()

            send_otp_email(email, otp, user.user_name)

            return Response({
                "data": None,
                "message": "OTP sent to email.",
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)

        raise ValidationException(
            detail="Invalid email",
            context=serializer.errors
        )


class VerifyEmailOTPView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VerifyEmailOTPSerializer(data=request.data)

        if serializer.is_valid():
            return Response({
                "data": None,
                "message": "Email verified successfully.",
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)

        if "Email already verified." in serializer.errors.get("non_field_errors", []):
            return Response({
                "data": None,
                "message": "Email already verified.",
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)

        raise ValidationException(
            detail="Invalid OTP",
            context=serializer.errors
        )


class UpdateUserInfoView(APIView):
    permission_classes = [IsAuthenticated]
    
    def patch(self, request):
        """
        Partial update of user information - PATCH method
        """
        serializer = FlexibleUpdateUserInfoSerializer(
            data=request.data,
            context={'user': request.user}
        )

        if serializer.is_valid():
            user = serializer.update(request.user, serializer.validated_data)
            
            return Response({
                "data": BaseUserSerializer(user).data,
                "message": "User information updated successfully.",
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)

        raise ValidationException(
            detail="Invalid data",
            context=serializer.errors
        )


class AdminUserListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        users = User.objects.all()
        serializer = AdminUserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminBlacklistedTokenListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        tokens = BlacklistedAccessToken.objects.all()
        serializer = BlacklistedAccessTokenSerializer(tokens, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)