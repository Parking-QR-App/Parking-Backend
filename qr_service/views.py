from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.utils import timezone
from .models import QRCode, QRCodeAnalytics
from common.authentication import generate_qr_code, decode_and_verify_qr_hash
import uuid
from django.conf import settings

class GenerateUserQRCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Generates a QR code for the authenticated user."""
        try:
            user = request.user
            
            # Check if user already has a QR code
            existing_qr = QRCode.objects.filter(user=user).first()
            if existing_qr:
                return Response(
                    {"error": "You already have a QR code.", "status": 400},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Ensure required data is present in the request
            first_name = request.data.get("first_name")
            last_name = request.data.get("last_name")
            email = request.data.get("email")

            if not first_name or not last_name or not email:
                return Response(
                    {"error": "First name, last name, and email are required.", "status": 400},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update user data
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.save()

            # Generate QR code
            qr_id = str(uuid.uuid4())
            qr_code = QRCode.objects.create(qr_id=qr_id, user=user)
            QRCodeAnalytics.objects.create(qr_code=qr_code)
            qr_link_code = generate_qr_code(qr_id)

            return Response(
                {
                    "qr": {
                        "domain": settings.BACKEND_URL,
                        "api_route": "/qr/scan-qr/",
                        "hashed_qr_id": qr_link_code
                    },
                     "message": "QR code generated.", 
                     "status": 201
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {"error": str(e), "status": 500},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GenerateAdminQRCodeView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        """Admin generates an unregistered QR code that any user can later register."""
        try:
            qr_id = str(uuid.uuid4())
            qr_code = QRCode.objects.create(qr_id=qr_id, user=None)
            QRCodeAnalytics.objects.create(qr_code=qr_code)
            qr_link_code = generate_qr_code(qr_id)

            return Response(
                {
                    "qr": {
                        "domain": settings.BACKEND_URL,
                        "api_route": "/qr/scan-qr/",
                        "hashed_qr_id": qr_link_code
                    },
                    "message": "Admin QR code generated.", 
                    "status": 201
                },
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {"error": str(e), "status": 500},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ScanQRCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, hashed_qr_id):
        try:
            qr_id = decode_and_verify_qr_hash(hashed_qr_id)
            if not qr_id:
                return Response({"error": "Invalid QR Code", "status": 400}, status=status.HTTP_400_BAD_REQUEST)

            try:
                qr_code = QRCode.objects.get(qr_id=qr_id)
                
                # Check if the QR code is active
                if not qr_code.is_active:
                    return Response({"message": "Cannot make call. QR code is deactivated.", "status": 403}, status=status.HTTP_403_FORBIDDEN)

                analytics, created = QRCodeAnalytics.objects.get_or_create(qr_code=qr_code)

                user = request.user if request.user.is_authenticated else None
                analytics.increment_scan_count(user)  # Update analytics

                if qr_code.user:
                    return Response({"message": "Make call", "status": 200}, status=status.HTTP_200_OK)
                else:
                    return Response({"message": "Register QR", "status": 200}, status=status.HTTP_200_OK)

            except QRCode.DoesNotExist:
                return Response({"error": "QR Code not found", "status": 404}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response(
                {"error": str(e), "status": 500},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ControlQRCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Allows a user to activate or deactivate their QR code."""
        try:
            user = request.user
            qr_code = QRCode.objects.filter(user=user).first()

            if not qr_code:
                return Response(
                    {"error": "No QR code found for this user.", "status": 404},
                    status=status.HTTP_404_NOT_FOUND
                )

            is_active = request.data.get("is_active")

            if is_active is None:
                return Response(
                    {"error": "is_active field is required.", "status": 400},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Convert to proper boolean
            if isinstance(is_active, str):
                is_active = is_active.lower() in ["true", "1"]
            qr_code.is_active = is_active
            qr_code.save(update_fields=['is_active'])  # Ensure only is_active is updated
            qr_code.refresh_from_db()  # Ensure data is refreshed from DB
            status_message = "QR code activated." if qr_code.is_active else "QR code deactivated."
            return Response({"message": status_message, "status": 200}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": str(e), "status": 500},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RegisterQRCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, hashed_qr_id):
        try:
            user = request.user
            qr_id = decode_and_verify_qr_hash(hashed_qr_id)

            if not qr_id:
                return Response(
                    {"error": "Invalid QR Code.", "status": 400},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check if the user already has a QR code registered
            if QRCode.objects.filter(user=user).exists():
                return Response(
                    {"error": "You already have a registered QR code.", "status": 400},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check if this QR ID already exists but without a user
            qr_code = QRCode.objects.filter(qr_id=qr_id).first()

            if qr_code:
                if qr_code.user:
                    return Response(
                        {"error": "This QR code is already registered by another user.", "status": 400},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                # Assign user to existing QR code
                qr_code.user = user
                qr_code.is_active = True
                qr_code.save()
            else:
                # Create a new QR code if it does not exist
                qr_code = QRCode.objects.create(
                    qr_id=qr_id,
                    user=user,
                    is_active=True,
                    created_at=timezone.now()
                )
                QRCodeAnalytics.objects.create(qr_code=qr_code)

            # Validate required user data
            first_name = request.data.get("first_name")
            last_name = request.data.get("last_name")
            email = request.data.get("email")

            if not first_name or not last_name or not email:
                return Response(
                    {"error": "First name, last name, and email are required.", "status": 400},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Update user data
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.save()

            qr_link_code = generate_qr_code(qr_id)

            return Response(
                {
                    "qr": {
                        "domain": settings.BACKEND_URL,
                        "api_route": "/qr/scan-qr/",
                        "hashed_qr_id": qr_link_code
                    },
                    "message": "QR code registered successfully.",
                    "status": 201
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            return Response(
                {"error": str(e), "status": 500},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class QRCodeAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, hashed_qr_id):
        try:
            qr_id = decode_and_verify_qr_hash(hashed_qr_id)
            if not qr_id:
                return Response({"error": "Invalid QR Code", "status": 400}, status=status.HTTP_400_BAD_REQUEST)

            try:
                analytics = QRCodeAnalytics.objects.get(qr_code_id=qr_id)
                data = {
                    "scan_count": analytics.scan_count,
                    "unique_users": analytics.unique_users,
                    "last_scanned": analytics.last_scanned,
                    "status": 200
                }
                return Response(data, status=status.HTTP_200_OK)

            except QRCodeAnalytics.DoesNotExist:
                return Response({"error": "No analytics found for this QR code", "status": 404}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response(
                {"error": str(e), "status": 500},
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
                {"total_qr_codes": total_qr_codes, "total_scans": total_scans, "unique_users": unique_users, "status": 200},
                status=status.HTTP_200_OK
            )

        except Exception as e:
            return Response(
                {"error": str(e), "status": 500},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
