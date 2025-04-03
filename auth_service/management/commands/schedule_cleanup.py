# auth_service/management/commands/schedule_cleanup.py

from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json

class Command(BaseCommand):
    help = "Schedules Celery task to clean up blacklisted tokens daily."

    def handle(self, *args, **kwargs):
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.DAYS,
        )

        task, created = PeriodicTask.objects.get_or_create(
            interval=schedule,
            name="Delete blacklisted tokens daily",
            task="auth_service.tasks.cleanup_blacklisted_tokens",
            defaults={'args': json.dumps([])},
        )

        if created:
            self.stdout.write(self.style.SUCCESS("Cleanup task scheduled successfully!"))
        else:
            self.stdout.write(self.style.WARNING("Cleanup task already exists."))
