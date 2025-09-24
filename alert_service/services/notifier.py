from django.core.cache import cache
from django.db import IntegrityError, DatabaseError
from ..models import Notification
from django.conf import settings
from shared.utils.api_exceptions import (
    ValidationException,
    ServiceUnavailableException,
    ConflictException
)
import logging

logger = logging.getLogger(__name__)

class Notifier:
    IDEMPOTENCY_PREFIX = "NOTIF:IDEMPOTENCY:"
    DEFAULT_IDEMPOTENCY_TTL = getattr(settings, "NOTIFICATION_IDEMPOTENCY_TTL", 86400)  # 24h default

    @classmethod
    def send_notification(
        cls,
        sender,
        receiver,
        notification_type,
        title,
        message,
        metadata=None,
        idempotency_key=None,
        immediate=True
    ):
        # Input validation
        if not receiver:
            raise ValidationException(
                detail="Receiver is required",
                context={'receiver': 'Receiver cannot be None'}
            )
        
        if not notification_type:
            raise ValidationException(
                detail="Notification type is required",
                context={'notification_type': 'Notification type cannot be empty'}
            )
        
        if not title:
            raise ValidationException(
                detail="Title is required",
                context={'title': 'Title cannot be empty'}
            )
        
        if not message:
            raise ValidationException(
                detail="Message is required",
                context={'message': 'Message cannot be empty'}
            )

        try:
            # Handle idempotency
            if idempotency_key:
                cache_key = f"{cls.IDEMPOTENCY_PREFIX}{idempotency_key}"
                try:
                    if cache.get(cache_key):
                        return None  # Already processed
                    cache.set(cache_key, True, timeout=cls.DEFAULT_IDEMPOTENCY_TTL)
                except Exception as e:
                    logger.warning(f"Cache error for idempotency key: {str(e)}")
                    # Continue without idempotency if cache fails

            # Create notification
            try:
                notification = Notification.objects.create(
                    sender=sender,
                    user=receiver,
                    type=notification_type,
                    title=title,
                    message=message,
                    metadata=metadata or {}
                )
            except IntegrityError as e:
                logger.error(f"Integrity error creating notification: {str(e)}")
                raise ConflictException(
                    detail="Notification creation conflict",
                    context={'reason': 'Database constraint violation'}
                )
            except DatabaseError as e:
                logger.error(f"Database error creating notification: {str(e)}")
                raise ServiceUnavailableException(
                    detail="Notification database temporarily unavailable"
                )

            # Queue notification delivery
            try:
                from ..tasks import deliver_notification_task
                if immediate:
                    deliver_notification_task.apply(args=[notification.id])
                else:
                    deliver_notification_task.delay(notification.id)
            except Exception as e:
                logger.error(f"Failed to queue notification delivery: {str(e)}")
                # Don't fail notification creation for delivery queue issues
                logger.warning(f"Notification {notification.id} created but delivery queue failed")

            return notification

        except ValidationException:
            raise
        except ConflictException:
            raise
        except ServiceUnavailableException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending notification: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Notification service temporarily unavailable",
                context={'user_message': 'Unable to send notification. Please try again.'}
            )
