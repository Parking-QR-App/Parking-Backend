from django.apps import apps

class NotificationModelService:
    _notification_model = None

    @classmethod
    def get_notification_model(cls):
        if cls._notification_model is None:
            cls._notification_model = apps.get_model('alert_service', 'Notification')
        return cls._notification_model