from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenRefreshView
from django.utils.timezone import now
from .models import User, BlacklistedAccessToken
from django.conf import settings
from django.core.exceptions import ValidationError
import smtplib
from shared.utils.api_exceptions import (
    AuthenticationException, ValidationException,
    ServiceUnavailableException, EmailServiceUnavailableException,
    EmailSendFailedException, ConflictException, NotFoundException
)
from .services.model_import_service import AuthService
from referral_service.services.model_import_service import ReferralModelService
from platform_settings.services.import_service import CallBalanceServiceLoader
from referral_service.services.import_service import ReferralServiceLoader

from .serializers import (
    RegisterSerializer, VerifyOTPSerializer, AdminUserSerializer,
    VerifyEmailOTPSerializer, EmailOTPSerializer, BlacklistedAccessTokenSerializer, BaseUserSerializer, FlexibleUpdateUserInfoSerializer
)
from .services.registration_service import RegistrationService
from .utils import send_otp_email, generate_otp
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.db import transaction, IntegrityError
from .throttles import AuthThrottle


import logging

logger = logging.getLogger(__name__)

class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh")
        BlacklistedAccessToken = AuthService.get_blacklisted_access_token_model()
        UserDevice = AuthService.get_user_device_model()

        if not refresh_token:
            raise ValidationException(
                detail="Missing refresh token",
                context={'refresh': 'Refresh token is required'}
            )

        try:
            refresh = RefreshToken(refresh_token)
            user = refresh.user

            # Get device info from headers (validated by middleware)
            device_id = request.headers.get("X-Device-ID")
            fcm_token = request.headers.get("X-FCM-Token")

            # Find the device (should exist due to middleware validation)
            device = None
            if device_id:
                try:
                    device = UserDevice.objects.get(user=user, device_id=device_id)
                except UserDevice.DoesNotExist:
                    # This shouldn't happen if middleware is working correctly
                    logger.warning(f"Device not found for user {user.id} with device_id {device_id}")

            # Blacklist old access token if device tracking is available
            if device and device.last_access_token:
                try:
                    BlacklistedAccessToken.objects.get_or_create(
                        token=device.last_access_token,
                        user=user
                    )
                except Exception as e:
                    logger.warning(f"Failed to blacklist old access token: {str(e)}")

            # Blacklist the used refresh token
            try:
                refresh.blacklist()
            except Exception as e:
                logger.warning(f"Failed to blacklist refresh token: {str(e)}")

            # Generate new tokens
            new_refresh = RefreshToken.for_user(user)
            new_access = new_refresh.access_token

            # Update device tracking if device exists
            if device:
                try:
                    device.last_refresh_token_jti = new_refresh['jti']
                    device.last_access_token = str(new_access)
                    device.last_active = timezone.now()
                    if fcm_token:
                        device.fcm_token = fcm_token
                    device.save()
                except Exception as e:
                    logger.warning(f"Failed to update device info: {str(e)}")

            return Response({
                'message': 'Token refreshed successfully',
                'data': {
                    'access': str(new_access),
                    'refresh': str(new_refresh),
                    'access_expires_in': settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds(),
                    'refresh_expires_in': settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds(),
                },
                'status': status.HTTP_200_OK
            }, status=status.HTTP_200_OK)

        except TokenError as e:
            raise AuthenticationException(
                detail="Token authentication failed",
                context={'refresh_token': 'Invalid or expired refresh token'}
            )
        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Token refresh service temporarily unavailable"
            )


class RegisterView(APIView):
    """Registration for regular users only"""
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            raise ValidationException(
                detail="Registration validation failed",
                context=serializer.errors
            )

        email = serializer.validated_data['email'].lower().strip()

        try:
            user, created = RegistrationService.register_user(email)

            return Response({
                'message': 'Registration successful. OTP sent to email.',
                'data': {
                    'email': user.email,
                    'user_id': user.user_id,
                    'is_new_user': created
                },
                'status': status.HTTP_201_CREATED if created else status.HTTP_200_OK
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        except ValidationError as ve:
            raise ValidationException(
                detail="Registration validation failed",
                context={'email': str(ve)}
            )
        except IntegrityError:
            raise ConflictException(
                detail="User already exists",
                context={'email': 'This email is already registered'}
            )

        # SMTP transport/provider outages (retryable, 503)
        except (smtplib.SMTPConnectError,
                smtplib.SMTPServerDisconnected,
                smtplib.SMTPHeloError,
                smtplib.SMTPAuthenticationError,
                TimeoutError) as e:
            logger.error(f"SMTP transport error for email {email}: {e}", exc_info=True)
            raise EmailServiceUnavailableException(
                detail="Email service temporarily unavailable",
                context={'email': email, 'reason': e.__class__.__name__}
            )

        # Upstream rejected the message (non-retryable now, 502)
        except (smtplib.SMTPSenderRefused,
                smtplib.SMTPRecipientsRefused,
                smtplib.SMTPDataError) as e:
            logger.warning(f"Email send rejected for {email}: {e}", exc_info=True)
            raise EmailSendFailedException(
                detail="Failed to send verification email",
                context={'email': email, 'reason': e.__class__.__name__}
            )

        # Generic SMTP error fallback
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error for {email}: {e}", exc_info=True)
            raise EmailServiceUnavailableException(
                detail="Email service temporarily unavailable",
                context={'email': email, 'reason': 'SMTPException'}
            )

        except Exception as e:
            logger.error(f"Registration failed for email {email}: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Registration service temporarily unavailable",
                context={'service': 'Unable to process registration at this time'}
            )

class VerifyOTPView(APIView):
    """OTP verification for regular users only"""
    permission_classes = [AllowAny]
    throttle_classes = [AuthThrottle]

    @transaction.atomic
    def post(self, request):
        """
        Verify OTP and complete user registration/login
        Handles both registration and login scenarios
        """
        serializer = VerifyOTPSerializer(data=request.data)
        
        # Enhanced validation with proper exception usage
        if not serializer.is_valid():
            # Transform Django validation errors to consistent format
            field_errors = {}
            for field, errors in serializer.errors.items():
                if isinstance(errors, list):
                    field_errors[field] = [str(error) for error in errors]
                else:
                    field_errors[field] = [str(errors)]
            
            raise ValidationException(
                detail="Please check your input and try again",  # User-friendly message
                context={
                    "fields": field_errors,
                    "suggestion": "Review the highlighted fields and try again"
                }
            )

        user = serializer.validated_data["user"]
        device_type = serializer.validated_data.get("device_type", "web")
        os_version = serializer.validated_data.get("os_version", "")
        fcm_token = request.headers.get("X-FCM-Token")
        device_id = request.headers.get("X-Device-ID")

        # Enhanced device validation with proper exceptions
        missing_headers = []
        if not fcm_token:
            missing_headers.append("X-FCM-Token")
        if not device_id:
            missing_headers.append("X-Device-ID")
            
        if missing_headers:
            raise ValidationException(
                detail="Device information is required to continue",
                context={
                    "missing_headers": missing_headers,
                    "suggestion": "Please ensure your app has necessary permissions and try again"
                }
            )

        # Validate device ID format
        if len(device_id) < 5 or len(device_id) > 255:
            raise ValidationException(
                detail="Invalid device identification",
                context={
                    "field": "device_id",
                    "requirement": "Must be 5-255 characters",
                    "suggestion": "Please restart the app or reinstall if issue persists"
                }
            )

        # Validate FCM token format
        if len(fcm_token) < 10:
            raise ValidationException(
                detail="Invalid notification configuration", 
                context={
                    "field": "fcm_token",
                    "requirement": "Must be at least 10 characters",
                    "suggestion": "Check your app's notification settings"
                }
            )

        try:
            # Check if this is first login (registration) or subsequent login
            CallBalanceService = CallBalanceServiceLoader.get_call_balance_service()
            UserDevice = AuthService.get_user_device_model()
            is_first_login = not user.email_verified
            user_created_recently = (timezone.now() - user.created_at).total_seconds() < 300

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
                    CallBalanceService.initialize_user_balance(user)
                    logger.info(f"Initialized call balance for user {user.user_id}")
                except Exception as e:
                    logger.error(f"Failed to initialize call balance for user {user.user_id}: {str(e)}")
                    # Don't fail the entire process for balance initialization failure

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
                    # Don't fail for email sending issues

            # 5. Fetch current balance
            current_balance = CallBalanceService.get_user_balance(user)

            # 6. Build consistent success response
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
                'is_new_user': is_first_login,
                'call_balance': {
                    'base': float(current_balance.base_balance),
                    'bonus': float(current_balance.bonus_balance),
                    'total': float(current_balance.total_balance),
                },
                'referral_data': referral_data
            }

            return Response({
                'success': True,
                'message': 'Registration completed successfully' if is_first_login else 'Login successful',
                'data': response_data,
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)

        except ValidationException:
            raise
        except AuthenticationException:
            raise
        except IntegrityError as e:
            logger.error(f"Database integrity error during OTP verification: {str(e)}")
            raise ConflictException(
                detail="We encountered an issue setting up your account",
                context={
                    "suggestion": "Please try again in a few moments"
                }
            )
        except Exception as e:
            logger.exception(f"Unexpected error during OTP verification: {str(e)}")
            raise ServiceUnavailableException(
                detail="Our service is temporarily unavailable",
                context={
                    "suggestion": "Please try again in 30 seconds",
                    "retry_after": 30
                }
            )

    def _process_pending_referral(self, user, request):
        """Process any pending referral or campaign code from session"""
        ReferralCode = ReferralModelService.get_referral_code_model()
        referral_data = {}
        User = AuthService.get_user_model()

        if not hasattr(request, 'session'):
            return referral_data

        referral_code = request.session.get("pending_referral_code")
        referrer_id = request.session.get("pending_referrer_id")
        code_type = request.session.get("pending_code_type")

        if referral_code and code_type:
            try:
                ReferralService = ReferralServiceLoader.get_referral_service()
                CampaignService = ReferralServiceLoader.get_campaign_service()

                if code_type == "user" and referrer_id:
                    # Handle normal referral
                    try:
                        referrer = User.objects.get(id=referrer_id)
                    except User.DoesNotExist:
                        logger.warning(f"Referrer not found: {referrer_id}")
                        return referral_data

                    code, error = ReferralService.validate_referral_code(referral_code)
                    if error:
                        logger.warning(f"Invalid pending referral code {referral_code}: {error}")
                        return referral_data

                    relationship = ReferralService.create_referral_relationship(referrer, user, code)
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

                    relationship = ReferralService.create_referral_relationship(None, user, code)
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

                # Clear session
                for key in ["pending_referral_code", "pending_referrer_id", "pending_code_type"]:
                    request.session.pop(key, None)
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
        """Clean up old devices and blacklist tokens"""
        BlacklistedAccessToken = AuthService.get_blacklisted_access_token_model()
        UserDevice = AuthService.get_user_device_model()
        
        try:
            # Get and cleanup old devices
            old_devices = user.devices.exclude(device_id=device_id)
            for old_device in old_devices:
                if old_device.last_access_token:
                    try:
                        BlacklistedAccessToken.objects.get_or_create(
                            token=old_device.last_access_token,
                            user=user
                        )
                    except Exception as e:
                        logger.warning(f"Failed to blacklist access token: {str(e)}")

                # Blacklist refresh token
                if old_device.last_refresh_token_jti:
                    try:
                        from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
                        outstanding_token = OutstandingToken.objects.filter(jti=old_device.last_refresh_token_jti).first()
                        if outstanding_token:
                            BlacklistedToken.objects.get_or_create(token=outstanding_token)
                    except Exception as e:
                        logger.warning(f"Failed to blacklist refresh token: {str(e)}")

            # Remove old devices
            old_devices.delete()
            
            # Remove devices with same device_id or fcm_token from other users
            UserDevice.objects.filter(device_id=device_id).exclude(user=user).delete()
            UserDevice.objects.filter(fcm_token=fcm_token).exclude(user=user).delete()
            
        except Exception as e:
            logger.error(f"Device cleanup failed: {str(e)}")
            # Don't fail the entire process if cleanup fails

    def get_client_ip(self, request):
        """Get client IP (existing logic preserved)"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')


class LogoutView(APIView):
    """Logout for regular users only"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh_token")
        fcm_token = request.headers.get("fcm_token")
        device_id = request.headers.get("X-Device-ID")
        
        BlacklistedAccessToken = AuthService.get_blacklisted_access_token_model()
        UserDevice = AuthService.get_user_device_model()

        # Validate required logout data
        if not refresh_token:
            raise ValidationException(
                detail="Missing refresh token",
                context={'refresh_token': 'Refresh token is required for logout'}
            )

        logout_errors = []
        logout_success = []

        # 1. Blacklist access token
        try:
            if request.auth:
                BlacklistedAccessToken.objects.get_or_create(
                    token=str(request.auth),
                    user=request.user
                )
                logout_success.append("access_token_blacklisted")
        except Exception as e:
            logout_errors.append(f"Access token blacklist failed: {str(e)}")
            logger.warning(f"Access token blacklist failed for user {request.user.id}: {str(e)}")

        # 2. Blacklist refresh token
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logout_success.append("refresh_token_blacklisted")
        except TokenError:
            raise AuthenticationException(
                detail="Invalid refresh token",
                context={'refresh_token': 'Refresh token is invalid or already blacklisted'}
            )
        except Exception as e:
            logout_errors.append(f"Refresh token blacklist failed: {str(e)}")
            logger.warning(f"Refresh token blacklist failed for user {request.user.id}: {str(e)}")

        # 3. Remove device registration (optional)
        if device_id or fcm_token:
            try:
                device_filter = {'user': request.user}
                if device_id:
                    device_filter['device_id'] = device_id
                if fcm_token:
                    device_filter['fcm_token'] = fcm_token
                
                deleted_count, _ = UserDevice.objects.filter(**device_filter).delete()
                if deleted_count > 0:
                    logout_success.append("device_unregistered")
                    
            except Exception as e:
                logout_errors.append(f"Device cleanup failed: {str(e)}")
                logger.warning(f"Device cleanup failed for user {request.user.id}: {str(e)}")

        # Return success even if some cleanup failed
        response_data = {
            'message': "Logged out successfully",
            'data': None,
            'status': status.HTTP_205_RESET_CONTENT,
        }

        if logout_errors:
            response_data['warnings'] = logout_errors
            
        return Response(response_data, status=status.HTTP_205_RESET_CONTENT)

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
    """Update user info for regular users only"""
    permission_classes = [IsAuthenticated]
    
    def patch(self, request):
        """Partial update of user information - PATCH method"""
        serializer = FlexibleUpdateUserInfoSerializer(
            data=request.data,
            context={'user': request.user}
        )

        if not serializer.is_valid():
            raise ValidationException(
                detail="User information validation failed",
                context=serializer.errors
            )

        try:
            user = serializer.update(request.user, serializer.validated_data)
            
            return Response({
                "data": BaseUserSerializer(user).data,
                "message": "User information updated successfully",
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)

        except ValidationError as ve:
            raise ValidationException(
                detail="User update validation failed",
                context={'validation': str(ve)}
            )
        except IntegrityError as ie:
            raise ConflictException(
                detail="User information conflict",
                context={'conflict': 'Data already exists or violates constraints'}
            )
        except Exception as e:
            logger.error(f"User info update failed: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="User update service temporarily unavailable"
            )
    
class ScanCarPlateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, car_plate_number):
        # Validate car plate number format
        if not car_plate_number or len(car_plate_number.strip()) < 2:
            raise ValidationException(
                detail="Invalid car plate number format",
                context={'car_plate_number': 'Car plate number must be at least 2 characters'}
            )

        User = AuthService.get_user_model()
        
        try:
            user = User.objects.get(license_plate_number=car_plate_number.upper().strip())
            
            return Response({
                "message": "User found successfully",
                "data": {
                    "zego_user_id": user.user_id,
                    "zego_user_name": user.user_name,
                    "license_plate": user.license_plate_number
                },
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)
        
        except User.DoesNotExist:
            raise NotFoundException(  # Better than ResourceNotFoundException
                detail="User not found",
                context={'car_plate_number': f'No user registered with plate number: {car_plate_number}'}
            )
        except User.MultipleObjectsReturned:
            logger.warning(f"Multiple users found for plate number: {car_plate_number}")
            raise ConflictException(
                detail="Multiple users found with same plate number",
                context={'car_plate_number': 'Data integrity issue - contact support'}
            )
        except Exception as e:
            logger.error(f"Car plate scan failed: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Car plate lookup service temporarily unavailable"
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
