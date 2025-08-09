from rest_framework import status
from utils.response_structure import error_response


class ReferralError(Exception):
    """Base for referral-related errors."""
    default_message = "An error occurred in referral processing"
    error_code = "referral_error"
    http_status = status.HTTP_400_BAD_REQUEST

    def __init__(self, message=None, *, details=None):
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)

    def to_response(self):
        return error_response(
            message=self.message,
            errors={'code': self.error_code, 'details': self.details},
            status=self.http_status
        )

    def as_dict(self):
        return {
            'message': self.message,
            'code': self.error_code,
            'details': self.details,
            'status': self.http_status,
        }


class CodeValidationError(ReferralError):
    """Invalid or unusable referral code."""
    default_message = "Referral code validation failed"
    error_code = "code_validation_error"
    http_status = status.HTTP_400_BAD_REQUEST

    def __init__(self, message=None, *, reason=None, details=None):
        self.reason = reason  # like 'inactive', 'expired', 'not_found'
        super().__init__(message=message, details=details or {})
        if self.reason:
            self.details['reason'] = self.reason


class RelationshipError(ReferralError):
    """Error applying or updating referral relationships."""
    default_message = "Referral relationship error"
    error_code = "relationship_error"
    http_status = status.HTTP_400_BAD_REQUEST


class LimitError(ReferralError):
    """Referral limit exceeded or suspended."""
    default_message = "Referral limit exceeded or suspended"
    error_code = "limit_error"
    http_status = status.HTTP_429_TOO_MANY_REQUESTS  # rate/limit semantics


class AdminOperationError(ReferralError):
    """Admin-level configuration failure."""
    default_message = "Admin operation failed"
    error_code = "admin_operation_error"
    http_status = status.HTTP_403_FORBIDDEN
