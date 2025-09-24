from importlib import import_module

class CallServiceLoader:
    _call_service = None
    _call_reconciliation_service = None

    @classmethod
    def get_call_service(cls):
        if cls._call_service is None:
            module = import_module('call_service.services.call_service')
            cls._call_service = module.CallService
        return cls._call_service
    
    @classmethod
    def get_call_reconciliation_service(cls):
        if cls._call_reconciliation_service is None:
            module = import_module('call_service.services.call_service')
            cls._call_reconciliation_service = module.CallReconciliationService
        return cls._call_reconciliation_service