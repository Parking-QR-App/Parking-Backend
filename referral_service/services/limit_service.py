from ..utils.limits import reset_limits_if_needed, check_and_consume_referral_quota
from ..services.exceptions import LimitError


class ReferralLimitScheduler:
    """
    Intended to be run periodically (e.g., Celery beat) to reset and optionally boost.
    """
    @staticmethod
    def run_reset_for_all():
        from ..models import ReferralLimit
        limits = ReferralLimit.objects.all()
        for limit in limits:
            reset_limits_if_needed(limit)

    @staticmethod
    def ensure_quota_and_consume(user, limit_type='daily'):
        try:
            return check_and_consume_referral_quota(user, limit_type=limit_type)
        except Exception as e:
            raise LimitError(str(e))
