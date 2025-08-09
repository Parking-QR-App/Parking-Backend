from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from ..models import ReferralCode
from ..utils.code import validate_referral_code_string, create_user_referral_code_if_eligible
from ..services.exceptions import CodeValidationError


class ReferralCodeService:
    @staticmethod
    def validate_code_format(code: str):
        if not validate_referral_code_string(code):
            raise CodeValidationError("Referral code format is invalid")

    @staticmethod
    def get_active_code(code: str) -> ReferralCode:
        ReferralCodeService.validate_code_format(code)
        try:
            rc = ReferralCode.objects.get(code=code)
        except ReferralCode.DoesNotExist:
            raise CodeValidationError("Referral code not found")

        if not rc.is_valid or rc.is_expired():  # active/valid, not expired:
            raise CodeValidationError("Referral code is not active or has expired")

        return rc

    @staticmethod
    def generate_for_user_if_eligible(user):
        """
        Create or return existing user-type referral code if user meets criteria.
        """
        return create_user_referral_code_if_eligible(user)

    @staticmethod
    def create_campaign_code(created_by, prefix: str = '', note: str = '') -> ReferralCode:
        """
        Admin creates a single campaign-type referral code (no external campaign model).
        """
        with transaction.atomic():
            code_str = None
            # Attempt to generate unique code with optional prefix
            for _ in range(5):
                random_part = ReferralCodeService._random_suffix()
                candidate = f"{prefix.upper()}{random_part}" if prefix else random_part
                if not ReferralCode.objects.filter(code=candidate).exists():
                    code_str = candidate
                    break
            if not code_str:
                # fallback deterministic
                code_str = timezone.now().strftime('%Y%m%d%H%M%S%f')[:12].upper()

            rc = ReferralCode.objects.create(
                code=code_str,
                code_type='campaign',
                status='active',
                created_by_admin=created_by,
                notes=note
            )
        return rc

    @staticmethod
    def bulk_create_campaign_codes(created_by, prefix: str, quantity: int, note: str = '') -> list[str]:
        """
        Admin bulk-generates `quantity` campaign codes with optional prefix.
        Returns list of code strings.
        """
        if quantity <= 0:
            raise ValidationError("Quantity must be positive")
        generated = []
        with transaction.atomic():
            for _ in range(quantity):
                code_str = None
                for _ in range(5):
                    random_part = ReferralCodeService._random_suffix()
                    candidate = f"{prefix.upper()}{random_part}" if prefix else random_part
                    if not ReferralCode.objects.filter(code=candidate).exists():
                        code_str = candidate
                        break
                if not code_str:
                    code_str = timezone.now().strftime('%Y%m%d%H%M%S%f')[:12].upper()

                rc = ReferralCode.objects.create(
                    code=code_str,
                    code_type='campaign',
                    status='active',
                    created_by_admin=created_by,
                    notes=note
                )
                generated.append(rc.code)
        return generated

    @staticmethod
    def _random_suffix():
        from django.utils.crypto import get_random_string
        return get_random_string(8, allowed_chars='ABCDEFGHJKLMNPQRSTUVWXYZ23456789').upper()
