from django.apps import apps

class PlatformSettingsModelService:
    _platform_setting = None
    _user_call_balance = None
    _balance_reset_log = None

    @classmethod
    def get_platform_settings_model(cls):
        if cls._platform_setting is None:
            cls._platform_setting = apps.get_model('platform_settings', 'PlatformSetting')
        return cls._platform_setting
    
    @classmethod
    def get_user_call_balance_model(cls):
        if cls._user_call_balance is None:
            cls._user_call_balance = apps.get_model('platform_settings', 'UserCallBalance')
        return cls._user_call_balance
    
    @classmethod
    def get_balance_reset_log_model(cls):
        if cls._balance_reset_log is None:
            cls._balance_reset_log = apps.get_model('platform_settings', 'BalanceResetLog')
        return cls._balance_reset_log
