from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenRefreshView
from django.utils.timezone import now
from .models import User, BlacklistedAccessToken, UserDevice
from qr_service.models import QRCode
from .serializers import (
    RegisterSerializer, VerifyOTPSerializer, UserSerializer,
    VerifyEmailOTPSerializer, EmailOTPSerializer, UpdateUserInfoSerializer, BlacklistedAccessTokenSerializer
)
from .utils import send_otp_email, generate_otp
from rest_framework_simplejwt.tokens import RefreshToken
import random  # For generating the OTP
from django.utils import timezone
from django.conf import settings
from auth_service.services.firestore_service import create_user_in_firestore
from common.authentication import generate_qr_code

class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        fcm_token = request.headers.get("FCM-TOKEN")
        device_id = request.headers.get("DEVICE-ID")
        refresh_token = request.data.get("refresh")

        if not fcm_token or not device_id:
            return Response({
                'message': 'Error',
                'errors': {'device': 'FCM-TOKEN and DEVICE-ID headers are required'},
                'status': status.HTTP_400_BAD_REQUEST
            }, status=status.HTTP_400_BAD_REQUEST)

        if not refresh_token:
            return Response({
                'message': 'Error',
                'errors': {'refresh': 'Refresh token is required'},
                'status': status.HTTP_400_BAD_REQUEST
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            refresh = RefreshToken(refresh_token)
            user = refresh.user

            device = UserDevice.objects.filter(user=user, device_id=device_id, fcm_token=fcm_token).first()
            if not device:
                return Response({
                    'message': 'Error',
                    'errors': {'device': 'Device not recognized or unauthorized'},
                    'status': status.HTTP_401_UNAUTHORIZED
                }, status=status.HTTP_401_UNAUTHORIZED)

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
            return Response({
                'message': 'Error',
                'errors': {'token': 'Invalid or expired refresh token'},
                'status': status.HTTP_401_UNAUTHORIZED
            }, status=status.HTTP_401_UNAUTHORIZED)

# Registration View (Sends OTP to user)
class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        try:
            otp = str(random.randint(100000, 999999))  # Generate OTP
            phone_number = request.data['phone_number']
            user = User.objects.filter(phone_number=phone_number).first()

            if user:
                user.otp = otp
                user.otp_expiry = now() + timezone.timedelta(minutes=5)
                user.save()
                return Response({
                    'phone_number': user.phone_number,
                    'otp': user.otp,
                    'message': 'OTP updated for existing phone number.',
                    'status': status.HTTP_200_OK
                }, status=status.HTTP_200_OK)
            else:
                firebase_user_profile = create_user_in_firestore(phone_number)
                user = User.objects.create(
                    phone_number=phone_number,
                    otp=otp,
                    otp_expiry=now() + timezone.timedelta(minutes=5),
                    user_id=firebase_user_profile['uid'],  # Overwrite UUIDField with Firebase UID
                    user_name=firebase_user_profile['username']
                )
                return Response({
                    'phone_number': user.phone_number,
                    'otp': user.otp,
                    'message': 'New user created and OTP sent.',
                    'status': status.HTTP_201_CREATED
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(e)
            return Response({
                'error': str(e),
                'message': 'Something went wrong while registering.',
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# OTP Verification View (Handles OTP verification for login)
class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        print(request.data)
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            print(serializer.errors)
            return Response({
                'message': 'Error',
                'errors': serializer.errors,
                'status': status.HTTP_400_BAD_REQUEST
            }, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data["user"]
        device_type = serializer.validated_data.get("device_type")
        fcm_token = request.headers.get("X-FCM-Token")
        device_id = request.headers.get("X-Device-ID")

        if not fcm_token or not device_id:
            print('FCM-TOKEN and DEVICE-ID headers are required')
            return Response({
                'message': 'Error',
                'errors': {'headers': 'FCM-TOKEN and DEVICE-ID headers are required'},
                'status': status.HTTP_400_BAD_REQUEST
            }, status=status.HTTP_400_BAD_REQUEST)

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
        # Save new device
        device, _ = UserDevice.objects.update_or_create(
            user=user,
            device_id=device_id,
            defaults={
                "user": user,
                'fcm_token': fcm_token,
                'device_type': device_type,
                "device_id": device_id,
                'os_version': serializer.validated_data.get("os_version"),
                'ip_address': self.get_client_ip(request),
                'last_active': now(),
            }
        )
        
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        device.last_access_token = str(access)
        device.last_refresh_token_jti = refresh['jti']
        device.save()

        # Optional: Fetch active QR Code info
        qr_info = ''
        qr_code = QRCode.objects.filter(user=user, is_active=True).first()
        if qr_code:
            qr_info = {
                "domain": settings.BACKEND_URL,
                "api_route": "/qr/scan-qr/",
                "hashed_qr_id": str(generate_qr_code(qr_code.qr_id, qr_code.created_at))
            }

        return Response({
            'message': 'Login successful',
            'data': {
                'access_token': str(access),
                'refresh_token': str(refresh),
                'user_id': user.user_id,
                'user_name': user.user_name,
                'email': user.email if user.email_verified else "",
                'first_name': user.first_name or "",
                'last_name': user.last_name or "",
                'active_devices': user.devices.count(),  # New helpful field
                'qr': qr_info
            },
            'status': status.HTTP_200_OK
        })

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

    
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
            return Response(status=status.HTTP_400_BAD_REQUEST)


# Send Email OTP View (Sends OTP to user's email)
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

            send_otp_email(email, otp)

            return Response({
                "data": None,
                "message": "OTP sent to email.",
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)

        return Response({
            "error": serializer.errors,
            "message": "Invalid email.",
            "status": status.HTTP_400_BAD_REQUEST
        }, status=status.HTTP_400_BAD_REQUEST)


# Verify Email OTP View (Verifies the OTP entered by the user)
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
        print(serializer.errors)
        return Response({
            "error": serializer.errors,
            "message": "Invalid OTP.",
            "status": status.HTTP_400_BAD_REQUEST
        }, status=status.HTTP_400_BAD_REQUEST)

    
class UpdateUserInfoView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        serializer = UpdateUserInfoSerializer(data=request.data)

        if serializer.is_valid():
            user = request.user
            serializer.update(user, serializer.validated_data)

            return Response({
                "data": None,
                "message": "User information updated successfully.",
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)

        return Response({
            "error": serializer.errors,
            "message": "Invalid data.",
            "status": status.HTTP_400_BAD_REQUEST
        }, status=status.HTTP_400_BAD_REQUEST)


class AdminUserListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        users = User.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminBlacklistedTokenListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        tokens = BlacklistedAccessToken.objects.all()
        serializer = BlacklistedAccessTokenSerializer(tokens, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)