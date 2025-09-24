from importlib import import_module

class RegistrationServiceLoader:
    _registration_service = None

    @classmethod
    def get_referral_service(cls):
        if cls._registration_service is None:
            module = import_module('auth_service.services.registration_service')
            cls._registration_service = module.RegistrationService
        return cls._registration_service