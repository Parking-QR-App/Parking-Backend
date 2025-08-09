from ..utils.events import log_event
from ..services.exceptions import ReferralError


class ReferralEventService:
    @staticmethod
    def record(user, event_type, **kwargs):
        try:
            return log_event(user=user, event_type=event_type, **kwargs)
        except Exception as e:
            raise ReferralError(f"Failed to log event: {str(e)}")
