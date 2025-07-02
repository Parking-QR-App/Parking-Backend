from django.core.cache import cache
from ..models import Notification

class Notifier:
    @classmethod
    def send_notification(
        cls,
        sender,         # Can be User object or None
        receiver,       # User object or ID
        notification_type,
        title,
        message,
        metadata=None,
        idempotency_key=None,
        immediate=True
    ):
        """
        Creates and dispatches a notification
        
        Args:
            immediate: If True, sends synchronously (for critical alerts)
        """
        # Idempotency check
        if idempotency_key and cache.get(f"notif:{idempotency_key}"):
            return None
            
        cache.set(f"notif:{idempotency_key}", True, timeout=86400)  # 24h

        # Handle sender (can be User object, ID, or None)
        # sender_id = None
        # if sender is not None:
        #     sender_id = sender.id if hasattr(sender, 'id') else sender

        # # Handle receiver
        # receiver_id = receiver.id if hasattr(receiver, 'id') else receiver
        # Create notification record
        notification = Notification.objects.create(
            sender=sender,  # Add sender
            user=receiver,
            type=notification_type,
            title=title,
            message=message,
            metadata=metadata or {}
        )

        # Dispatch
        if immediate:
            from ..tasks import deliver_notification_task
            deliver_notification_task.apply(args=[notification.id])  # Synchronous
        else:
            from ..tasks import deliver_notification_task
            print("SENDER1")
            deliver_notification_task.delay(notification.id)  # Async
            
        return notification