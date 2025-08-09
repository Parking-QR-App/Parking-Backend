from ..models import ReferralLimit


def on_referral_verified(relationship):
    """
    Called when referred user completes verification (OTP/email).
    Updates:
      - referrer's ReferralLimit: successful_referrals, verified_referrals
      - referral code: total_registrations, total_verified_users
    """
    referrer = relationship.referrer
    # Ensure referral limit exists
    try:
        limit = referrer.referral_limits
    except ReferralLimit.DoesNotExist:
        limit = ReferralLimit.objects.create(user=referrer)

    # Increment once per verified referral
    limit.verified_referrals += 1
    limit.successful_referrals += 1
    limit.save(update_fields=['verified_referrals', 'successful_referrals', 'updated_at'])

    # Update the referral code metrics
    code = relationship.referral_code_used
    code.total_registrations += 1
    code.total_verified_users += 1
    code.save(update_fields=['total_registrations', 'total_verified_users', 'updated_at'])


def on_referral_converted(relationship):
    """
    Called when referred user makes first payment.
    Updates:
      - referrer's ReferralLimit: paying_referrals
      - referral code: total_paying_users, total_revenue_generated
      - fills days_to_first_payment if missing
    """
    referrer = relationship.referrer
    # Ensure referral limit exists
    try:
        limit = referrer.referral_limits
    except ReferralLimit.DoesNotExist:
        limit = ReferralLimit.objects.create(user=referrer)

    limit.paying_referrals += 1
    limit.save(update_fields=['paying_referrals', 'updated_at'])

    code = relationship.referral_code_used
    amount = relationship.first_payment_amount or 0
    code.total_paying_users += 1
    code.total_revenue_generated = (code.total_revenue_generated or 0) + amount
    code.save(update_fields=['total_paying_users', 'total_revenue_generated', 'updated_at'])

    # Compute days_to_first_payment if not already
    if relationship.first_payment_at and relationship.created_at:
        delta = relationship.first_payment_at - relationship.created_at
        relationship.days_to_first_payment = delta.days
        relationship.save(update_fields=['days_to_first_payment', 'updated_at'])
