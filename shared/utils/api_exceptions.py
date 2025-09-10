# shared/utils/api_exceptions.py
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from typing import Optional, Dict, Any
from shared.logging_context import correlation_id_var
import logging

logger = logging.getLogger(__name__)



class BaseServiceException(APIException):
    """Base exception for all service exceptions"""
    default_code = "service_error"
    default_detail = "A service error occurred"

    def __init__(
        self,
        detail: Optional[str] = None,
        code: Optional[str] = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        context: Optional[Dict[str, Any]] = None,
    ):
        # Ensure .code is always set
        resolved_code = code or getattr(self, "default_code", "error")
        resolved_detail = detail or getattr(self, "default_detail", "An error occurred")

        super().__init__(detail=resolved_detail, code=resolved_code)
        self.status_code = status_code
        self.code = resolved_code
        self.detail = resolved_detail
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": getattr(self, "code", "error"),
                "message": str(self.detail),
                "status_code": self.status_code,
                "context": self.context,
                "type": self.__class__.__name__,
            }
        }

# ------------------------
# Service Communication
# ------------------------
class ServiceCallException(BaseServiceException):
    default_code = 'service_call_failed'
    default_detail = 'Service call failed'
    status_code = status.HTTP_502_BAD_GATEWAY


class ServiceTimeoutException(ServiceCallException):
    default_code = 'service_timeout'
    default_detail = 'Service call timed out'
    status_code = status.HTTP_504_GATEWAY_TIMEOUT


class ServiceUnavailableException(ServiceCallException):
    default_code = 'service_unavailable'
    default_detail = 'Service is temporarily unavailable'
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class ServiceTemporarilyUnavailable(BaseServiceException):
    default_code = "service_unavailable"
    default_detail = "Service temporarily unavailable"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class CircuitOpenException(BaseServiceException):
    default_code = "circuit_open"
    default_detail = "Circuit open for dependent service"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


# ------------------------
# Migration
# ------------------------
class MigrationException(BaseServiceException):
    default_code = 'migration_failed'
    default_detail = 'Data migration failed'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class MigrationLockException(MigrationException):
    default_code = 'migration_locked'
    default_detail = 'Migration is already in progress'
    status_code = status.HTTP_423_LOCKED


class DataValidationException(MigrationException):
    default_code = 'data_validation_failed'
    default_detail = 'Data validation failed during migration'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


# ------------------------
# Business Logic
# ------------------------
class InsufficientBalanceException(BaseServiceException):
    default_code = 'insufficient_balance'
    default_detail = 'Insufficient call balance'
    status_code = status.HTTP_402_PAYMENT_REQUIRED


class RewardExpiredException(BaseServiceException):
    default_code = 'reward_expired'
    default_detail = 'Reward has expired'
    status_code = status.HTTP_410_GONE


class SubscriptionRequiredException(BaseServiceException):
    default_code = 'subscription_required'
    default_detail = 'Active subscription required'
    status_code = status.HTTP_403_FORBIDDEN


class InsufficientRewardValueException(BaseServiceException):
    default_code = "insufficient_value"
    default_detail = "Insufficient reward value"
    status_code = status.HTTP_400_BAD_REQUEST


class InvalidStateTransitionException(BaseServiceException):
    default_code = "invalid_state"
    default_detail = "Invalid state transition"
    status_code = status.HTTP_409_CONFLICT


class FraudDetectedException(BaseServiceException):
    default_code = "fraud_detected"
    default_detail = "Fraudulent activity detected"
    status_code = status.HTTP_403_FORBIDDEN

class NotFoundException(BaseServiceException):
    default_code = "not_found"
    default_detail = "Resource not found"
    status_code = status.HTTP_404_NOT_FOUND


# ------------------------
# Rate Limiting
# ------------------------
class RateLimitExceededException(BaseServiceException):
    default_code = "rate_limit_exceeded"
    default_detail = "Rate limit exceeded"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS

    def __init__(self, retry_after: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        if retry_after:
            # DRF handlers pick this header up
            self.headers = {"Retry-After": str(retry_after)}


class RateLimitExceeded(BaseServiceException):
    default_code = "rate_limited"
    default_detail = "Rate limit exceeded"
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


# ------------------------
# Validation
# ------------------------
class InvalidRequestException(BaseServiceException):
    default_code = 'invalid_request'
    default_detail = 'Invalid request parameters'
    status_code = status.HTTP_400_BAD_REQUEST


class ResourceNotFoundException(BaseServiceException):
    default_code = 'resource_not_found'
    default_detail = 'Requested resource not found'
    status_code = status.HTTP_404_NOT_FOUND


class ConflictException(BaseServiceException):
    default_code = 'conflict'
    default_detail = 'Resource conflict occurred'
    status_code = status.HTTP_409_CONFLICT


class CampaignValidationException(BaseServiceException):
    default_code = "campaign_validation_failed"
    default_detail = "Campaign validation failed"
    status_code = status.HTTP_400_BAD_REQUEST


class ReferralException(BaseServiceException):
    default_code = "referral_operation_failed"
    default_detail = "Referral operation failed"
    status_code = status.HTTP_400_BAD_REQUEST



class ValidationException(BaseServiceException):
    default_code = "validation_error"
    default_message = "Validation failed"
    default_status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail=None, context=None, code=None):
        self.code = code or self.default_code
        self.detail = detail or self.default_message
        self.context = context or {}
        super().__init__(self.detail, code=self.code, status_code=self.default_status_code, context=self.context)



# ------------------------
# Authentication & Authorization
# ------------------------
class AuthenticationException(BaseServiceException):
    default_code = 'authentication_failed'
    default_detail = 'Authentication failed'
    status_code = status.HTTP_401_UNAUTHORIZED


class AuthorizationException(BaseServiceException):
    default_code = 'authorization_failed'
    default_detail = 'Authorization failed'
    status_code = status.HTTP_403_FORBIDDEN


class PermissionDeniedException(BaseServiceException):
    default_code = "permission_denied"
    default_detail = "You do not have permission to perform this action"
    status_code = status.HTTP_403_FORBIDDEN

# ==================== REWARD-SPECIFIC EXCEPTIONS ====================

class RewardValidationException(ValidationException):
    """Reward-specific validation errors"""
    default_code = 'reward_validation_error'
    default_detail = 'Reward validation failed'

class RewardNotFoundException(NotFoundException):
    """Reward not found"""
    default_code = 'reward_not_found'
    default_detail = 'Reward not found'

class RewardLimitExceededException(RateLimitExceededException):
    """Reward limit exceeded"""
    default_code = 'reward_limit_exceeded'
    default_detail = 'Reward limit exceeded'

class RewardStateException(InvalidStateTransitionException):
    """Invalid reward state"""
    default_code = 'invalid_reward_state'
    default_detail = 'Invalid reward state for operation'

class RewardExpiredException(BaseServiceException):
    """Reward has expired"""
    default_code = 'reward_expired'
    default_detail = 'Reward has expired'
    status_code = status.HTTP_410_GONE  # HTTP_410_GONE

class InsufficientRewardValueException(BaseServiceException):
    """Insufficient reward value"""
    default_code = 'insufficient_reward_value'
    default_detail = 'Insufficient reward value'
    status_code = status.HTTP_400_BAD_REQUEST  # HTTP_400_BAD_REQUEST

class CampaignValidationException(ValidationException):
    """Campaign validation failed"""
    default_code = 'campaign_validation_failed'
    default_detail = 'Campaign validation failed'

class CampaignNotFoundException(NotFoundException):
    """Campaign not found"""
    default_code = 'campaign_not_found'
    default_detail = 'Campaign not found'

class EntitlementValidationException(ValidationException):
    """Entitlement validation failed"""
    default_code = 'entitlement_validation_failed'
    default_detail = 'Entitlement validation failed'

class RedemptionValidationException(ValidationException):
    """Redemption validation failed"""
    default_code = 'redemption_validation_failed'
    default_detail = 'Redemption validation failed'

class ReconciliationException(BaseServiceException):
    """Reconciliation error"""
    default_code = 'reconciliation_error'
    default_detail = 'Reconciliation failed'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR  # HTTP_500_INTERNAL_SERVER_ERROR

class AnalyticsException(BaseServiceException):
    """Analytics error"""
    default_code = 'analytics_error'
    default_detail = 'Analytics processing failed'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR  # HTTP_500_INTERNAL_SERVER_ERROR

# ------------------------
# Handler
# ------------------------

def format_exception_response(exc, context=None):
    """
    Convert exceptions into consistent JSON + inject correlation ID
    """
    request = context.get("request") if context else None

    # Pull correlation ID from request if available, otherwise from contextvars
    correlation_id = getattr(request, "correlation_id", None) or correlation_id_var.get()

    # Case 1: Our custom BaseServiceException
    if isinstance(exc, BaseServiceException):
        response_data = exc.to_dict()

    # Case 2: DRF APIException (e.g. ValidationError)
    elif isinstance(exc, APIException):
        response_data = {
            "error": {
                "code": getattr(exc, "code", getattr(exc, "default_code", "error")),
                "message": str(getattr(exc, "detail", exc)),
                "status_code": getattr(
                    exc, "status_code", status.HTTP_400_BAD_REQUEST
                ),
                "type": exc.__class__.__name__,
                "context": getattr(exc, "context", {}),
            }
        }

    # Case 3: Unexpected exception
    else:
        response_data = {
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "type": "UnexpectedException",
            }
        }
        logger.error(f"Unexpected exception: {str(exc)}", exc_info=True)

    # ✅ Always inject correlation ID
    response_data["error"]["correlation_id"] = correlation_id

    return Response(response_data, status=response_data["error"]["status_code"])


def exception_handler(exc, context):
    """
    Custom exception handler for DRF
    """
    return format_exception_response(exc, context)