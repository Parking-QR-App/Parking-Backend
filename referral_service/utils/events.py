from ..models import ReferralEvent
from django.utils import timezone

# Event type constants to avoid typos
EVENT_TYPE_CODE_GENERATED = 'code_generated'
EVENT_TYPE_CODE_SHARED = 'code_shared'
EVENT_TYPE_REGISTRATION_COMPLETED = 'registration_completed'
EVENT_TYPE_EMAIL_VERIFIED = 'email_verified'
EVENT_TYPE_FIRST_PAYMENT = 'first_payment'
EVENT_TYPE_REWARD_GIVEN = 'reward_given'
EVENT_TYPE_LIMIT_REACHED = 'limit_reached'
EVENT_TYPE_CODE_EXPIRED = 'code_expired'

VALID_EVENT_TYPES = {
    EVENT_TYPE_CODE_GENERATED,
    EVENT_TYPE_CODE_SHARED,
    EVENT_TYPE_REGISTRATION_COMPLETED,
    EVENT_TYPE_EMAIL_VERIFIED,
    EVENT_TYPE_FIRST_PAYMENT,
    EVENT_TYPE_REWARD_GIVEN,
    EVENT_TYPE_LIMIT_REACHED,
    EVENT_TYPE_CODE_EXPIRED,
}


def log_event(
    user,
    event_type: str,
    referral_code=None,
    referral_relationship=None,
    metadata: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    device_type: str | None = None
) -> ReferralEvent:
    """
    Generic recorder for referral-related events.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(f"Invalid event type: {event_type}")

    metadata = metadata or {}

    event = ReferralEvent.objects.create(
        event_type=event_type,
        user=user,
        referral_code=referral_code,
        referral_relationship=referral_relationship,
        metadata=metadata,
        ip_address=ip_address,
        user_agent=user_agent or '',
        device_type=device_type or '',
        created_at=timezone.now()
    )
    return event
