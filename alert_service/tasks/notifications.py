from celery import shared_task
from django.db.models import F
from ..models import Notification
from ..services.fcm_client import FCMClient

@shared_task(bind=True, max_retries=3)
def deliver_notification_task(self, notification_id):
    notification = Notification.objects.get(id=notification_id)
    print("Initial")
    success = FCMClient.send(
        user_id=notification.user_id,
        notification_id=notification.id,
        title=notification.title,
        body=notification.message,
        data={
            "type": notification.type,
            "route": f"/notifications/{notification.id}",
            **notification.metadata
        }
    )
    print("worked")
    if success:
        print("worked2")
        notification.is_delivered = True
        notification.save(update_fields=['is_delivered'])
    else:
        notification.delivery_attempts = F('delivery_attempts') + 1
        notification.save()
        self.retry(countdown=60 * self.request.retries)  # 1min, 2min, 3min