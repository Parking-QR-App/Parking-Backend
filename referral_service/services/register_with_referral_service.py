import logging
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from ..services.referral_relationship_service import ReferralRelationshipService
from ..utils.code import preflight_validate_referral_application
from ..utils.events import log_event, EVENT_TYPE_REGISTRATION_COMPLETED
from ..services.exceptions import CodeValidationError

# Note: auth_service.RegisterView is expected to exist in auth_service.views
from auth_service.views import RegisterView  # per instructions, use existing RegisterView

logger = logging.getLogger(__name__)


class RegisterWithReferralService:
    def __init__(self, reward_granter=None):
        # reward_granter signature: grant(referrer, referred_user, trigger_event, relationship, **kwargs)
        self.relationship_service = ReferralRelationshipService(reward_granter=reward_granter)

    def _call_auth_register(self, request):
        """
        Delegates to the auth service's RegisterView. Returns its Response.
        """
        return RegisterView().post(request)

    def register(self, request):
        """
        Full orchestration: user registration + optional referral application + reward logging.
        Returns a dict with:
          - auth_response
          - referral_relationship (if applied)
          - referral_error (if any)
          - reward_info (placeholder)
        """
        referral_code = request.data.get('referral_code')
        device_id = request.headers.get('X-Device-ID') or request.data.get('device_id')
        ip_address = self._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:1000]
        device_type = request.headers.get('X-Device-Type', '')

        result = {
            'auth_response': None,
            'referral_relationship': None,
            'referral_error': None,
            'reward_info': None,
        }

        # 1. If referral code provided, validate it first (fail fast)
        if referral_code:
            if not device_id:
                result['referral_error'] = "Device ID missing; required to process referral"
                return result

            try:
                # Validate referral code before user creation
                preflight_validate_referral_application(referral_code, referred_user=None)  # We'll validate user later
            except (ValidationError, CodeValidationError) as e:
                logger.warning(f"Referral validation failed pre-registration: {e}")
                result['auth_response'] = None
                result['referral_error'] = str(e)
                return result
            except Exception as e:
                logger.error(f"Unexpected error during referral pre-validation: {e}")
                result['referral_error'] = "An unexpected error occurred during referral validation"
                return result

        # 2. Call auth service registration (now safe to proceed)
        auth_response = self._call_auth_register(request)
        result['auth_response'] = auth_response

        if auth_response.status_code != 201:
            return result  # user creation failed; propagate upstream

        # 3. Fetch created user — assume phone_number is in request.data and is the USERNAME_FIELD
        phone_number = request.data.get('phone_number')
        if not phone_number:
            result['referral_error'] = "Phone number missing from registration payload"
            return result

        User = get_user_model()
        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            result['referral_error'] = "User created but not found by phone number"
            return result

        # 4. Log registration completion event
        log_event(
            user=user,
            event_type=EVENT_TYPE_REGISTRATION_COMPLETED,
            metadata={'via': 'register_with_referral'},
            ip_address=ip_address,
            user_agent=user_agent,
            device_type=device_type
        )

        # 5. Apply referral code (already validated above)
        if referral_code:
            try:
                # Re-validate with actual user context
                preflight_validate_referral_application(referral_code, user)

                relationship = self.relationship_service.register_with_code(
                    referral_code, user,
                    request_meta={
                        'REMOTE_ADDR': ip_address,
                        'HTTP_USER_AGENT': user_agent,
                        'DEVICE_TYPE': device_type
                    }
                )
                result['referral_relationship'] = relationship
            except (ValidationError, CodeValidationError) as e:
                logger.warning(f"Referral code application failed after registration for user {user.id}: {e}")
                result['referral_error'] = str(e)
            except Exception as e:
                logger.error(f"Unexpected error applying referral code for user {user.id}: {e}")
                result['referral_error'] = "An unexpected error occurred while applying referral code"

        return result

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')
