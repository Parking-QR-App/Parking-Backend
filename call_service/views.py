from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from .models import Call
from .serializers import CallSerializer
from .services import create_call, end_call, get_call_history, get_all_calls
from .utils import success_response, error_response


class StartCallAPIView(APIView):
    """User can initiate a Jitsi call. Calls are limited to 3 minutes max."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        guest_id = request.data.get("guest_id")

        if not guest_id:
            return error_response("Guest ID is required")

        call, error = create_call(user, guest_id)
        if error:
            return error_response(error)

        return success_response(
            data={
                "room_name": call.room_name,
                "expires_in": 180  # 3 minutes
            },
            message="Call started successfully",
            status_code=status.HTTP_201_CREATED
        )


class EndCallAPIView(APIView):
    """Users can end a call manually."""
    permission_classes = [IsAuthenticated]

    def post(self, request, call_id):
        call = get_object_or_404(Call, id=call_id)

        if request.user not in [call.host, call.guest]:
            return error_response("You are not authorized to end this call", status.HTTP_403_FORBIDDEN)

        error = end_call(call)
        if error:
            return error_response(error)

        return success_response(message="Call ended successfully")


class MyCallHistoryAPIView(APIView):
    """Users can view their own call history."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        calls = get_call_history(request.user)
        serializer = CallSerializer(calls, many=True)
        return success_response(data=serializer.data, message="Call history retrieved")


class AdminCallListAPIView(APIView):
    """Admin can view all calls."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        calls = get_all_calls()
        serializer = CallSerializer(calls, many=True)
        return success_response(data=serializer.data, message="Admin retrieved all calls")


class AdminEndCallAPIView(APIView):
    """Admin can forcibly end a call (useful for abuse handling)."""
    permission_classes = [IsAdminUser]

    def post(self, request, call_id):
        call = get_object_or_404(Call, id=call_id)

        error = end_call(call, status="failed")
        if error:
            return error_response(error)

        return success_response(message="Call forcibly ended by admin")
