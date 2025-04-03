from django.db.models.signals import pre_delete
from django.dispatch import receiver
from .models import Call
from django.contrib.auth import get_user_model

User = get_user_model()


@receiver(pre_delete, sender=User)
def handle_user_deletion(sender, instance, **kwargs):
    """Ends any ongoing calls if a user is deleted."""
    ongoing_calls = Call.objects.filter(
        call_status="ongoing",
        host=instance
    ) | Call.objects.filter(
        call_status="ongoing",
        guest=instance
    )

    for call in ongoing_calls:
        call.call_status = "failed"
        call.end_time = timezone.now()
        call.save()
