from django.utils import timezone
from ..models import ReferralRelationship

def mark_referral_converted(relationship: ReferralRelationship, first_payment_amount=None):
    """
    Mark a referral as converted (e.g., on first payment) and update timestamps.
    """
    now = timezone.now()
    updated = False

    if relationship.status not in ('converted', 'rewarded'):
        relationship.status = 'verified'
        updated = True

    if first_payment_amount is not None and not relationship.first_payment_at:
        relationship.first_payment_at = now
        relationship.first_payment_amount = first_payment_amount
        updated = True

    if updated:
        relationship.updated_at = now
        relationship.save()

    return relationship
