from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from .serializers import NotificationCreateSerializer, NotificationSerializer
from ...services.notifier import Notifier
from ...models.notification import Notification
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
from django.contrib.auth import get_user_model

class NotificationAPI(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='10/m', method='POST', block=True))
    def post(self, request):
        serializer = NotificationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "message": "Invalid input",
                "errors": serializer.errors,
                "status": status.HTTP_400_BAD_REQUEST
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Get the receiver user object
            User = get_user_model()
            try:
                receiver = User.objects.get(user_id=serializer.validated_data['receiver_id'])
            except User.DoesNotExist:
                    return Response({
                    "message": "Receiver not found",
                    "errors": {"receiver_id": "Invalid user ID"},
                    "status": status.HTTP_404_NOT_FOUND
                }, status=status.HTTP_404_NOT_FOUND)


            notification = Notifier.send_notification(
                sender=request.user,
                receiver=receiver,  # Pass user object instead of ID
                notification_type=Notification.Type.PARKING_ALERT,
                title=serializer.validated_data['title'],
                message=serializer.validated_data['message'],
                metadata=serializer.validated_data.get('metadata', {}),
                idempotency_key=serializer.validated_data.get('idempotency_key')
            )

            return Response({
                "message": "Notification sent",
                "data": {
                    "notification_id": str(notification.id),
                    "route": f"/notifications/{notification.id}"
                },
                "status": status.HTTP_201_CREATED
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                "message": "Error sending notification",
                "errors": {"exception": str(e)},
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationDetailAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, notification_id):
        try:
            notification = Notification.objects.get(id=notification_id, user=request.user)

            if not notification.is_read:
                notification.mark_as_read()

            return Response({
                "message": "Notification fetched",
                "data": NotificationSerializer(notification).data,
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)

        except ObjectDoesNotExist:
            return Response({
                "message": "Notification not found",
                "errors": {"notification_id": "Invalid or unauthorized access"},
                "status": status.HTTP_404_NOT_FOUND
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            print("❌ Exception in NotificationDetailAPI:", e)
            return Response({
                "message": "Failed to retrieve notification",
                "errors": {"exception": str(e)},
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NotificationListAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Use the correct related_name
            notifications = Notification.objects.filter(
                user=request.user,
                is_read=False
            )
            print(notifications)
            serializer = NotificationSerializer(notifications, many=True)
            print(serializer)
            return Response({
                "message": "Unread notifications fetched",
                "data": serializer.data,
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({
                "message": "Error fetching notifications",
                "errors": {"exception": str(e)},
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MarkAllAsReadAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            updated = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
            return Response({
                "message": "All notifications marked as read",
                "data": {"marked_read": updated},
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({
                "message": "Failed to mark notifications as read",
                "errors": {"exception": str(e)},
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UnreadCountAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            count = request.user.notifications.filter(is_read=False).count()
            return Response({
                "message": "Unread count fetched",
                "data": {"count": count},
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "message": "Failed to fetch unread count",
                "errors": {"exception": str(e)},
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)