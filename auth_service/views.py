from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.utils.timezone import now
from .models import User, BlacklistedAccessToken, UserDevice
from qr_service.models import QRCode
from .serializers import (
    RegisterSerializer, VerifyOTPSerializer, UserSerializer,
    VerifyEmailOTPSerializer, EmailOTPSerializer, UpdateUserInfoSerializer
)
from .utils import send_otp_email, generate_otp
from rest_framework_simplejwt.tokens import RefreshToken
import random  # For generating the OTP
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.conf import settings

# Registration View (Sends OTP to user)
class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        try:
            otp = str(random.randint(100000, 999999))
            phone_number = request.data['phone_number']
            user = User.objects.filter(phone_number=phone_number).first()

            if user:
                user.otp = otp
                user.otp_expiry = now() + timezone.timedelta(minutes=5)
                user.save()
                return Response({
                    'data': {
                        'phone_number': user.phone_number,
                        'otp': user.otp
                    },
                    'message': 'OTP updated for existing phone number.',
                    'status': status.HTTP_200_OK
                }, status=status.HTTP_200_OK)
            else:
                user = User.objects.create(
                    phone_number=phone_number,
                    otp=otp,
                    otp_expiry=now() + timezone.timedelta(minutes=5)
                )
                return Response({
                    'data': {
                        'phone_number': user.phone_number,
                        'otp': user.otp
                    },
                    'message': 'New user created and OTP sent.',
                    'status': status.HTTP_201_CREATED
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                'error': str(e),
                'message': 'Something went wrong while registering.',
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# OTP Verification View (Handles OTP verification for login)
class VerifyOTPView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)

        if serializer.is_valid():
            validated_data = serializer.validated_data
            user = validated_data["user"]
            fcm_token = validated_data.get("fcm_token")
            device_type = validated_data.get("device_type")

            if fcm_token and device_type:
                existing_device = UserDevice.objects.filter(fcm_token=fcm_token).first()

                if existing_device and existing_device.user != user:
                    return Response({
                        "error": {"fcm_token": "This FCM token is already registered to another user."},
                        "message": "Failed to register device.",
                        "status": status.HTTP_400_BAD_REQUEST
                    }, status=status.HTTP_400_BAD_REQUEST)

                if existing_device and existing_device.device_type != device_type:
                    existing_device.device_type = device_type
                    existing_device.save()
                elif not existing_device:
                    UserDevice.objects.create(user=user, fcm_token=fcm_token, device_type=device_type)

            refresh = RefreshToken.for_user(user)
            qr_info = None
            qr_code = QRCode.objects.filter(user=user, is_active=True).first()
            if qr_code:
                qr_info = {
                    "domain": settings.BACKEND_URL,
                    "api_route": "/qr/scan-qr/",
                    "hashed_qr_id": str(qr_code.qr_id)
                }

            return Response({
                'data': {
                    'access_token': str(refresh.access_token),
                    'refresh_token': str(refresh),
                    'first_name': user.first_name or "",
                    'last_name': user.last_name or "",
                    'email': user.email or "",
                    'qr': qr_info
                },
                'message': 'Login successful',
                'status': status.HTTP_200_OK
            }, status=status.HTTP_200_OK)

        return Response({
            'error': serializer.errors,
            'message': 'Invalid OTP',
            'status': status.HTTP_400_BAD_REQUEST
        }, status=status.HTTP_400_BAD_REQUEST)

    
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            access_token = request.auth
            refresh_token = request.data.get("refresh_token")

            if access_token:
                BlacklistedAccessToken.objects.create(token=str(access_token))

            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()

            return Response({
                'data': None,
                'message': "Logged out successfully.",
                'status': status.HTTP_205_RESET_CONTENT
            }, status=status.HTTP_205_RESET_CONTENT)

        except Exception as e:
            return Response({
                'error': str(e),
                'message': 'Failed to logout.',
                'status': status.HTTP_400_BAD_REQUEST
            }, status=status.HTTP_400_BAD_REQUEST)


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
