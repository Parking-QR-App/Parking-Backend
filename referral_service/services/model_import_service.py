from django.apps import apps

class ReferralModelService:
    _referral_code = None
    _referral_relationship = None
    _referral_settings = None

    @classmethod
    def get_referral_code_model(cls):
        if cls._referral_code is None:
            cls._referral_code = apps.get_model('referral_service', 'ReferralCode')
        return cls._referral_code
    
    @classmethod
    def get_referral_relationship_model(cls):
        if cls._referral_relationship is None:
            cls._referral_relationship = apps.get_model('referral_service', 'ReferralRelationship')
        return cls._referral_relationship  
    
    @classmethod
    def get_referral_settings_model(cls):
        if cls._referral_settings is None:
            cls._referral_settings = apps.get_model('referral_service', 'ReferralSettings')
        return cls._referral_settings  
    