from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from django.db import DatabaseError
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings
import logging

from .serializers import NotificationCreateSerializer, NotificationSerializer
from ...services.notifier import Notifier
from ...services.model_import_service import NotificationModelService
from rest_framework.permissions import IsAuthenticated
from auth_service.services.model_import_service import AuthService

# Import proper API exceptions
from shared.utils.api_exceptions import (
    ValidationException,
    NotFoundException,
    ServiceUnavailableException,
    ConflictException
)

logger = logging.getLogger(__name__)

class NotificationAPI(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='10/m', method='POST', block=True))
    def post(self, request):
        Notification = NotificationModelService.get_notification_model()
        serializer = NotificationCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            raise ValidationException(
                detail="Notification validation failed",
                context=serializer.errors
            )

        try:
            # Get the receiver user object
            User = AuthService.get_user_model()
            receiver_id = serializer.validated_data['receiver_id']
            
            try:
                receiver = User.objects.get(user_id=receiver_id)
            except User.DoesNotExist:
                raise NotFoundException(
                    detail="Receiver not found",
                    context={'receiver_id': f'No user found with ID: {receiver_id}'}
                )

            # Send notification
            notification = Notifier.send_notification(
                sender=request.user,
                receiver=receiver,
                notification_type=Notification.Type.PARKING_ALERT,
                title=serializer.validated_data['title'],
                message=serializer.validated_data['message'],
                metadata=serializer.validated_data.get('metadata', {}),
                idempotency_key=serializer.validated_data.get('idempotency_key')
            )

            # Handle idempotency case
            if notification is None:
                raise ConflictException(
                    detail="Duplicate notification request",
                    context={
                        'idempotency_key': serializer.validated_data.get('idempotency_key'),
                        'reason': 'Notification already sent'
                    }
                )

            return Response({
                "message": "Notification sent successfully",
                "data": {
                    "notification_id": str(notification.id),
                    "route": f"/notifications/{notification.id}"
                },
                "status": status.HTTP_201_CREATED
            }, status=status.HTTP_201_CREATED)

        except ValidationException:
            raise
        except NotFoundException:
            raise
        except ConflictException:
            raise
        except DatabaseError as e:
            logger.error(f"Database error sending notification: {str(e)}")
            raise ServiceUnavailableException(
                detail="Notification database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Unexpected error sending notification: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Notification service temporarily unavailable",
                context={'user_message': 'Unable to send notification. Please try again.'}
            )

class NotificationDetailAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, notification_id):
        # Validate notification_id
        if not notification_id:
            raise ValidationException(
                detail="Notification ID is required",
                context={'notification_id': 'Notification ID cannot be empty'}
            )

        Notification = NotificationModelService.get_notification_model()
        
        try:
            notification = Notification.objects.get(id=notification_id, user=request.user)

            # Mark as read if not already read
            if not notification.is_read:
                try:
                    notification.mark_as_read()
                except Exception as e:
                    logger.warning(f"Failed to mark notification as read: {str(e)}")
                    # Continue even if marking as read fails

            return Response({
                "message": "Notification retrieved successfully",
                "data": NotificationSerializer(notification).data,
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)

        except Notification.DoesNotExist:
            raise NotFoundException(
                detail="Notification not found",
                context={
                    'notification_id': notification_id,
                    'reason': 'Notification does not exist or access denied'
                }
            )
        except DatabaseError as e:
            logger.error(f"Database error retrieving notification: {str(e)}")
            raise ServiceUnavailableException(
                detail="Notification database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Unexpected error retrieving notification: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Notification retrieval service temporarily unavailable"
            )

class NotificationListAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        Notification = NotificationModelService.get_notification_model()
        
        try:
            notifications = Notification.objects.filter(
                user=request.user,
                is_read=False
            ).order_by('-created_at')  # Add ordering for consistency

            serializer = NotificationSerializer(notifications, many=True)
            
            return Response({
                "message": "Unread notifications retrieved successfully",
                "data": serializer.data,
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)
            
        except DatabaseError as e:
            logger.error(f"Database error fetching notifications: {str(e)}")
            raise ServiceUnavailableException(
                detail="Notification database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Unexpected error fetching notifications: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Notification list service temporarily unavailable"
            )

class MarkAllAsReadAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification = NotificationModelService.get_notification_model()
        
        try:
            updated = Notification.objects.filter(
                user=request.user, 
                is_read=False
            ).update(is_read=True)
            
            logger.info(f"Marked {updated} notifications as read for user {request.user.id}")
            
            return Response({
                "message": "All notifications marked as read successfully",
                "data": {"marked_read": updated},
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)
            
        except DatabaseError as e:
            logger.error(f"Database error marking notifications as read: {str(e)}")
            raise ServiceUnavailableException(
                detail="Notification update database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Unexpected error marking notifications as read: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Notification update service temporarily unavailable"
            )

class UnreadCountAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            count = request.user.notifications.filter(is_read=False).count()
            
            return Response({
                "message": "Unread count retrieved successfully",
                "data": {"count": count},
                "status": status.HTTP_200_OK
            }, status=status.HTTP_200_OK)
            
        except DatabaseError as e:
            logger.error(f"Database error fetching unread count: {str(e)}")
            raise ServiceUnavailableException(
                detail="Notification count database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Unexpected error fetching unread count: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Notification count service temporarily unavailable"
            )
