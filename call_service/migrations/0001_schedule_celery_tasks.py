from django.db import migrations
from django_celery_beat.models import PeriodicTask, IntervalSchedule
import json

def schedule_auto_end_task(apps, schema_editor):
    """Schedules the Celery task to auto-end calls exceeding 3 minutes."""
    
    # Create an interval (runs every minute)
    schedule, created = IntervalSchedule.objects.get_or_create(
        every=1,
        period=IntervalSchedule.MINUTES
    )

    # Create a periodic task for auto-ending calls
    PeriodicTask.objects.create(
        interval=schedule,
        name="Auto End Expired Calls",
        task="call_service.tasks.auto_end_expired_calls",
        args=json.dumps([]),  # No arguments needed
        enabled=True,
    )

def remove_auto_end_task(apps, schema_editor):
    """Removes the scheduled Celery task on migration rollback."""
    PeriodicTask.objects.filter(name="Auto End Expired Calls").delete()

class Migration(migrations.Migration):

    dependencies = [
        ("call_service", "0001_initial"),  # Replace with the last migration name
        ("django_celery_beat", "0001_initial"),  # Ensure Celery Beat migrations are applied
    ]

    operations = [
        migrations.RunPython(schedule_auto_end_task, remove_auto_end_task),
    ]
