from django.apps import apps

class CallModelService:
    _call_record = None
    _call_event_log = None

    @classmethod
    def get_call_record_model(cls):
        if cls._call_record is None:
            cls._call_record = apps.get_model('call_service', 'CallRecord')
        return cls._call_record
    
    @classmethod
    def get_call_event_log_model(cls):
        if cls._call_event_log is None:
            cls._call_event_log = apps.get_model('call_service', 'CallEventLog')
        return cls._call_event_log
