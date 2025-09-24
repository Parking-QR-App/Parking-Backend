from importlib import import_module

class CallBalanceServiceLoader:
    _settings_service = None
    _call_balance_service = None

    @classmethod
    def get_settings_service(cls):
        if cls._settings_service is None:
            module = import_module('platform_settings.services.settings_service')
            cls._settings_service = module.SettingsService
        return cls._settings_service

    @classmethod
    def get_call_balance_service(cls):
        if cls._call_balance_service is None:
            module = import_module('platform_settings.services.settings_service')
            cls._call_balance_service = module.CallBalanceService
        return cls._call_balance_service
