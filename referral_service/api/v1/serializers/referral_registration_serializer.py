from rest_framework import serializers
from ..serializers.relationship_serializer import ReferralRelationshipSerializer
from django.contrib.auth import get_user_model

User = get_user_model()

class ReferralRegistrationSerializer(serializers.Serializer):
    """
    Input/Output wrapper for register-with-referral flow.
    Expects the registration payload to be consumed by auth_service; includes optional referral_code.
    """
    referral_code = serializers.CharField(required=False, allow_blank=True)
    phone_number = serializers.CharField()  # for identifying user after registration

    # Output
    referral_relationship = ReferralRelationshipSerializer(read_only=True, required=False)
    referral_error = serializers.CharField(read_only=True, required=False)
    # auth_response is returned directly by view; could be embedded as raw dict if needed.

    def to_representation(self, instance):
        # instance is the dict returned from service.register(...)
        auth_resp = instance.get('auth_response')
        referral_rel = instance.get('referral_relationship')
        referral_error = instance.get('referral_error')

        data = {}
        # Flatten auth service response
        if hasattr(auth_resp, 'data'):
            data.update({'user': auth_resp.data})
        else:
            data.update({'user': None})

        if referral_rel:
            data['referral_relationship'] = ReferralRelationshipSerializer(referral_rel).data
        if referral_error:
            data['referral_error'] = referral_error

        return {
            'data': data,
            'message': 'Registration completed',
            'status': auth_resp.status_code if hasattr(auth_resp, 'status_code') else 200
        }

    def validate_referral_code(self, value):
        # basic non-empty check; detailed validation happens in service
        if value and not isinstance(value, str):
            raise serializers.ValidationError("Referral code must be a string")
        return value
