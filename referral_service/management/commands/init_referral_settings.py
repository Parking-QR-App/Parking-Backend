# referral_service/management/commands/init_referral_settings.py
from django.core.management.base import BaseCommand
from referral_service.services import ReferralService

class Command(BaseCommand):
    help = 'Initialize default referral settings'
    
    def handle(self, *args, **options):
        defaults = {
            'default_reward_calls': '5.00',
            'allow_self_referral': 'false',
            'max_user_codes': '1',
            'referral_code_length': '8',
        }
        
        for key, value in defaults.items():
            ReferralService.set_referral_settings(key, value, f"Default {key}")
        
        self.stdout.write(
            self.style.SUCCESS(f'Initialized {len(defaults)} referral settings')
        )