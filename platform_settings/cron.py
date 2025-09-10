from celery.schedules import crontab

# Celery Beat Schedule for platform settings tasks
PLATFORM_SETTINGS_BEAT_SCHEDULE = {
    'automated-balance-reset-daily': {
        'task': 'platform_settings.tasks.automated_balance_reset',
        'schedule': crontab(hour=2, minute=0),  # Run daily at 2 AM
        'options': {'queue': 'cron'}
    },
    'cleanup-old-logs-weekly': {
        'task': 'platform_settings.tasks.cleanup_old_logs',
        'schedule': crontab(day_of_week=0, hour=3, minute=0),  # Run weekly on Sunday at 3 AM
        'options': {'queue': 'cron'}
    },
}
