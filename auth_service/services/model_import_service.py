from django.apps import apps

class AuthService:
    _user_model = None
    _blacklisted_access_token = None
    _user_device = None
    _admin_session = None

    @classmethod
    def get_user_model(cls):
        if cls._user_model is None:
            cls._user_model = apps.get_model('auth_service', 'User')
        return cls._user_model

    @classmethod
    def get_user(cls, user_id):
        User = cls.get_user_model()
        return User.objects.get(id=user_id)
    
    @classmethod
    def get_blacklisted_access_token_model(cls):
        if cls._blacklisted_access_token is None:
            cls._blacklisted_access_token = apps.get_model('auth_service', 'BlacklistedAccessToken')
        return cls._blacklisted_access_token
    
    @classmethod
    def get_user_device_model(cls):
        if cls._user_device is None:
            cls._user_device = apps.get_model('auth_service', 'UserDevice')
        return cls._user_device
    
    @classmethod
    def get_admin_session_model(cls):
        if cls._admin_session is None:
            cls._admin_session = apps.get_model('auth_service', 'AdminSession')
        return cls._admin_session
