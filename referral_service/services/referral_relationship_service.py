from django.core.exceptions import ValidationError
from django.utils import timezone

from ..models import ReferralRelationship
from ..utils.relationship import mark_referral_converted
from ..utils.referral_application import apply_referral_code_for_registration
from ..utils.events import log_event, EVENT_TYPE_FIRST_PAYMENT, EVENT_TYPE_REWARD_GIVEN
from ..services.exceptions import RelationshipError
from ..utils.metrics import on_referral_converted
from django.utils import timezone


class ReferralRelationshipService:
    def __init__(self, reward_granter=None):
        """
        reward_granter: callable to grant rewards, signature like
            grant(referrer, referred_user, trigger_event, relationship)
        """
        self.reward_granter = reward_granter

    def register_with_code(self, referral_code: str, new_user, request_meta: dict):
        """
        Apply referral during registration, create relationship, and log event.
        """
        ip = request_meta.get('REMOTE_ADDR')
        user_agent = request_meta.get('HTTP_USER_AGENT', '')[:1000]
        device_type = request_meta.get('DEVICE_TYPE', '')
        try:
            relationship = apply_referral_code_for_registration(
                referrer_code=referral_code,
                referred_user=new_user,
                ip_address=ip,
                device_type=device_type,
                user_agent=user_agent
            )
        except ValidationError as e:
            raise RelationshipError(str(e))

        # Optionally grant registration reward
        if self.reward_granter:
            try:
                self.reward_granter(
                    referrer=relationship.referrer,
                    referred_user=new_user,
                    trigger_event='registration',
                    relationship=relationship
                )
                # mark reward given event
                log_event(
                    user=new_user,
                    event_type=EVENT_TYPE_REWARD_GIVEN,
                    referral_relationship=relationship,
                    metadata={'for': 'registration'},
                    ip_address=ip,
                    user_agent=user_agent,
                    device_type=device_type
                )
                # update relationship status
                relationship.status = 'rewarded'
                relationship.referrer_rewarded_at = timezone.now()
                relationship.referred_user_rewarded_at = timezone.now()
                relationship.save(update_fields=[
                    'status', 'referrer_rewarded_at', 'referred_user_rewarded_at', 'updated_at'
                ])
            except Exception:
                # reward failures shouldn't break core referral creation, but log separately in real system
                pass

        return relationship

    def mark_converted(self, relationship: ReferralRelationship, payment_amount=None, request_meta: dict = None):
        """
        On first payment or conversion event.
        """
        ip = request_meta.get('REMOTE_ADDR') if request_meta else None
        user_agent = request_meta.get('HTTP_USER_AGENT', '')[:1000] if request_meta else ''
        device_type = request_meta.get('DEVICE_TYPE', '') if request_meta else ''
        # Update conversion
        updated = mark_referral_converted(relationship, first_payment_amount=payment_amount)

        # Log event
        log_event(
            user=relationship.referred_user,
            event_type=EVENT_TYPE_FIRST_PAYMENT,
            referral_relationship=relationship,
            referral_code=relationship.referral_code_used,
            metadata={'amount': str(payment_amount)},
            ip_address=ip,
            user_agent=user_agent,
            device_type=device_type
        )

        # Update metrics for conversion
        try:
            on_referral_converted(relationship)
        except Exception:
            # don't crash on metric updating
            pass

        # Trigger reward if configured
        if self.reward_granter:
            try:
                self.reward_granter(
                    referrer=relationship.referrer,
                    referred_user=relationship.referred_user,
                    trigger_event='first_payment',
                    relationship=relationship,
                    payment_amount=payment_amount
                )
                log_event(
                    user=relationship.referred_user,
                    event_type=EVENT_TYPE_REWARD_GIVEN,
                    referral_relationship=relationship,
                    metadata={'for': 'first_payment'},
                    ip_address=ip,
                    user_agent=user_agent,
                    device_type=device_type
                )
                # update rewarded timestamps
                if not relationship.referrer_rewarded_at:
                    relationship.referrer_rewarded_at = timezone.now()
                if not relationship.referred_user_rewarded_at:
                    relationship.referred_user_rewarded_at = timezone.now()
                relationship.status = 'rewarded'
                relationship.save(update_fields=[
                    'referrer_rewarded_at', 'referred_user_rewarded_at', 'status', 'updated_at'
                ])
            except Exception:
                pass

        return updated
