from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules

class AlertServiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'alert_service'
    verbose_name = 'Alert Service'

    def ready(self):
        """
        Initialize app when Django starts.
        Triggers model registration and signal connections.
        """
        # Auto-discover tasks.py for Celery
        autodiscover_modules('tasks')
        
        # Connect signals (noqa prevents IDE warnings)
        # from . import signals  # noqa
        
        # Initialize FCM client if needed
        try:
            from .services import FCMClient
            FCMClient.initialize()
        except ImportError:
            pass