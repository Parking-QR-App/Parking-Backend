from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.utils import timezone
from .models import QRCode, QRCodeAnalytics
from common.authentication import generate_qr_code, decode_and_verify_qr_hash
import uuid
from django.conf import settings

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
import uuid

# Assuming generate_qr_code and decode_and_verify_qr_hash are defined elsewhere

class GenerateUserQRCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user = request.user

            if not user.email_verified:
                return Response(
                    {
                        "error": True,
                        "message": "Please verify your email before generating a QR code.",
                        "status": status.HTTP_403_FORBIDDEN,
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            if QRCode.objects.filter(user=user).exists():
                return Response(
                    {
                        "error": True,
                        "message": "You already have a QR code.",
                        "status": status.HTTP_400_BAD_REQUEST,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            first_name = request.data.get("first_name")
            last_name = request.data.get("last_name")
            email = request.data.get("email")

            if not all([first_name, last_name, email]):
                return Response(
                    {
                        "error": True,
                        "message": "First name, last name, and email are required.",
                        "status": status.HTTP_400_BAD_REQUEST,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.first_name = first_name
            user.last_name = last_name
            user.email = email.lower()
            user.save()

            qr_id = str(uuid.uuid4())
            qr_code = QRCode.objects.create(qr_id=qr_id, user=user)
            QRCodeAnalytics.objects.create(qr_code=qr_code)
            qr_link_code = generate_qr_code(qr_id, qr_code.created_at)

            return Response(
                {
                    "data": {
                        "qr": {
                            "domain": settings.BACKEND_URL,
                            "api_route": "/qr/scan-qr/",
                            "hashed_qr_id": qr_link_code,
                        }
                    },
                    "message": "QR code generated.",
                    "status": status.HTTP_201_CREATED
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response(
                {
                    "error": True,
                    "message": str(e),
                    "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class GenerateAdminQRCodeView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        try:
            qr_id = str(uuid.uuid4())
            qr_code = QRCode.objects.create(qr_id=qr_id, user=None)
            QRCodeAnalytics.objects.create(qr_code=qr_code)
            qr_link_code = generate_qr_code(qr_id)

            return Response(
                {
                    "data": {
                        "qr": {
                            "domain": settings.BACKEND_URL,
                            "api_route": "/qr/scan-qr/",
                            "hashed_qr_id": qr_link_code,
                        }
                    },
                    "message": "Admin QR code generated.", 
                    "status": status.HTTP_201_CREATED
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {
                    "error": True,
                    "message": str(e),
                    "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ScanQRCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, hashed_qr_id):
        try:
            qr_id = decode_and_verify_qr_hash(hashed_qr_id)
            if not qr_id:
                return Response(
                    {"error": "Invalid QR Code", "status": status.HTTP_400_BAD_REQUEST},
                    status=status.HTTP_400_BAD_REQUEST
                )
            qr_code = QRCode.objects.get(qr_id=qr_id)
            try:
                qr_code = QRCode.objects.get(qr_id=qr_id)

                # Check if the QR code is active
                if not qr_code.is_active:
                    return Response(
                        {"message": "Cannot make call. QR code is deactivated.", "status": status.HTTP_403_FORBIDDEN},
                        status=status.HTTP_403_FORBIDDEN
                    )
                print("QR:", qr_code)
                analytics, created = QRCodeAnalytics.objects.get_or_create(qr_code=qr_code)

                scanning_user = request.user if request.user.is_authenticated else None
                print("USER:", scanning_user)
                analytics.increment_scan_count(scanning_user)  # Update analytics
                print("ANALYTICS:", analytics)
                if qr_code.user:
                    # 🔁 Fetch the QR owner's user_id and user_name
                    qr_owner = qr_code.user
                    return Response(
                        {
                            "message": "Make call",
                            "data": {
                                "zego_user_id": qr_owner.user_id,
                                "zego_user_name": qr_owner.user_name,
                            },
                            "status": status.HTTP_200_OK
                        },
                        status=status.HTTP_200_OK
                    )
                else:
                    return Response(
                        {"message": "Register QR", "status": status.HTTP_200_OK},
                        status=status.HTTP_200_OK
                    )

            except QRCode.DoesNotExist:
                return Response(
                    {"error": "QR Code not found", "status": status.HTTP_404_NOT_FOUND},
                    status=status.HTTP_404_NOT_FOUND
                )

        except Exception as e:
            print(e)
            return Response(
                {"error": str(e), "status": status.HTTP_500_INTERNAL_SERVER_ERROR},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ControlQRCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            user = request.user
            qr_code = QRCode.objects.filter(user=user).first()

            if not qr_code:
                return Response(
                    {
                        "error": True,
                        "message": "No QR code found for this user.",
                        "status": status.HTTP_404_NOT_FOUND,
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            is_active = request.data.get("is_active")

            if is_active is None:
                return Response(
                    {
                        "error": True,
                        "message": "is_active field is required.",
                        "status": status.HTTP_400_BAD_REQUEST,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if isinstance(is_active, str):
                is_active = is_active.lower() in ["true", "1"]

            qr_code.is_active = is_active
            qr_code.save(update_fields=["is_active"])
            qr_code.refresh_from_db()

            return Response(
                {
                    "message": "QR code activated." if qr_code.is_active else "QR code deactivated.",
                    "status": status.HTTP_200_OK,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {
                    "error": True,
                    "message": str(e),
                    "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RegisterQRCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, hashed_qr_id):
        try:
            user = request.user

            # Check if user's email is verified
            if not user.email_verified:
                return Response(
                    {
                        "error": "Email not verified.",
                        "message": "Please verify your email before registering a QR code.",
                        "status": status.HTTP_403_FORBIDDEN
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            qr_id = decode_and_verify_qr_hash(hashed_qr_id)

            if not qr_id:
                return Response(
                    {
                        "error": "Invalid QR Code.",
                        "message": "The provided QR code is invalid.",
                        "status": status.HTTP_400_BAD_REQUEST
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            if QRCode.objects.filter(user=user).exists():
                return Response(
                    {
                        "error": "User already registered QR code.",
                        "message": "You already have a registered QR code.",
                        "status": status.HTTP_400_BAD_REQUEST
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            qr_code = QRCode.objects.filter(qr_id=qr_id).first()

            if qr_code:
                if qr_code.user:
                    return Response(
                        {
                            "error": "QR code already registered.",
                            "message": "This QR code is already registered by another user.",
                            "status": status.HTTP_400_BAD_REQUEST
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                qr_code.user = user
                qr_code.is_active = True
                qr_code.save()
            else:
                qr_code = QRCode.objects.create(
                    qr_id=qr_id,
                    user=user,
                    is_active=True,
                    created_at=timezone.now()
                )
                QRCodeAnalytics.objects.create(qr_code=qr_code)

            first_name = request.data.get("first_name")
            last_name = request.data.get("last_name")
            email = request.data.get("email")

            if not first_name or not last_name or not email:
                return Response(
                    {
                        "error": "Missing user data.",
                        "message": "First name, last name, and email are required.",
                        "status": status.HTTP_400_BAD_REQUEST
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            user.first_name = first_name
            user.last_name = last_name
            user.email = email.lower()
            user.save()

            qr_link_code = generate_qr_code(qr_id)

            return Response(
                {
                    "data": {
                        "qr": {
                            "domain": settings.BACKEND_URL,
                            "api_route": "/qr/scan-qr/",
                            "hashed_qr_id": qr_link_code
                        }
                    },
                    "message": "QR code registered successfully.",
                    "status": status.HTTP_201_CREATED
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {
                    "error": str(e),
                    "message": "An unexpected error occurred during QR code registration.",
                    "status": status.HTTP_500_INTERNAL_SERVER_ERROR
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class QRCodeAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, hashed_qr_id):
        try:
            qr_id = decode_and_verify_qr_hash(hashed_qr_id)
            if not qr_id:
                return Response(
                    {
                        "error": "Invalid QR Code.",
                        "message": "The provided QR code is invalid.",
                        "status": status.HTTP_400_BAD_REQUEST
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                analytics = QRCodeAnalytics.objects.get(qr_code_id=qr_id)
                return Response(
                    {
                        "data": {
                            "scan_count": analytics.scan_count,
                            "unique_users": analytics.unique_users,
                            "last_scanned": analytics.last_scanned
                        },
                        "message": "QR analytics retrieved successfully.",
                        "status": status.HTTP_200_OK
                    },
                    status=status.HTTP_200_OK
                )

            except QRCodeAnalytics.DoesNotExist:
                return Response(
                    {
                        "error": "Analytics not found.",
                        "message": "No analytics found for this QR code.",
                        "status": status.HTTP_404_NOT_FOUND
                    },
                    status=status.HTTP_404_NOT_FOUND
                )

        except Exception as e:
            return Response(
                {
                    "error": str(e),
                    "message": "An unexpected error occurred while fetching analytics.",
                    "status": status.HTTP_500_INTERNAL_SERVER_ERROR
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminQRCodeAnalyticsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            total_qr_codes = QRCode.objects.count()
            total_scans = QRCodeAnalytics.objects.aggregate(total=models.Sum("scan_count"))["total"] or 0
            unique_users = QRCodeAnalytics.objects.aggregate(total=models.Sum("unique_users"))["total"] or 0

            return Response(
                {
                    "data": {
                        "total_qr_codes": total_qr_codes,
                        "total_scans": total_scans,
                        "unique_users": unique_users
                    },
                    "message": "Admin QR analytics fetched successfully.",
                    "status": status.HTTP_200_OK
                },
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {
                    "error": str(e),
                    "message": "An unexpected error occurred while fetching admin analytics.",
                    "status": status.HTTP_500_INTERNAL_SERVER_ERROR
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
