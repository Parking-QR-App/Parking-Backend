from importlib import import_module

class ReferralServiceLoader:
    _referral_service = None
    _campaign_service = None

    @classmethod
    def get_referral_service(cls):
        if cls._referral_service is None:
            module = import_module('referral_service.services.referral_service')
            cls._referral_service = module.ReferralService
        return cls._referral_service

    @classmethod
    def get_campaign_service(cls):
        if cls._campaign_service is None:
            module = import_module('referral_service.services.campaign_service')
            cls._campaign_service = module.CampaignService
        return cls._campaign_service