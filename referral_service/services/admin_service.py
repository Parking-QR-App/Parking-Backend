from ..utils.admin import set_user_limits, adjust_user_limits
from ..services.exceptions import AdminOperationError


class AdminReferralService:
    @staticmethod
    def set_limits(user, daily=None, weekly=None, monthly=None, total=None, actor=None, reason=''):
        try:
            return set_user_limits(
                user,
                daily=daily,
                weekly=weekly,
                monthly=monthly,
                total=total,
                actor=actor,
                reason=reason
            )
        except Exception as e:
            raise AdminOperationError(str(e))

    @staticmethod
    def adjust_limits(user, delta_daily=0, delta_weekly=0, delta_monthly=0, actor=None, reason=''):
        try:
            return adjust_user_limits(
                user,
                delta_daily=delta_daily,
                delta_weekly=delta_weekly,
                delta_monthly=delta_monthly,
                actor=actor,
                reason=reason
            )
        except Exception as e:
            raise AdminOperationError(str(e))
