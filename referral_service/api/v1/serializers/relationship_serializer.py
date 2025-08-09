from rest_framework import serializers
from django.contrib.auth import get_user_model
from ....models import ReferralRelationship
from ....services.referral_relationship_service import ReferralRelationshipService
from ....services.exceptions import RelationshipError, CodeValidationError

User = get_user_model()


class ApplyReferralCodeSerializer(serializers.Serializer):
    """
    Serializer used during registration to apply a referral code.
    """
    referral_code = serializers.CharField()
    referred_user_id = serializers.UUIDField()
    
    def validate_referral_code(self, value):
        from ....services.referral_code_service import ReferralCodeService
        try:
            ReferralCodeService.validate_code_format(value)
        except CodeValidationError as e:
            raise serializers.ValidationError(str(e))
        return value

    def validate_referred_user_id(self, value):
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Referred user not found")
        self.context['referred_user'] = user
        return value

    def validate(self, attrs):
        # Additional cross-field validation
        referral_code = attrs['referral_code']
        referred_user = self.context.get('referred_user')
        if not referred_user:
            raise serializers.ValidationError("Referred user must be provided")
        if referral_code and referred_user:
            # Ownership/self-referral check
            try:
                from ....services.referral_code_service import ReferralCodeService
                code_obj = ReferralCodeService.get_active_code(referral_code)
                if code_obj.owner == referred_user:
                    raise serializers.ValidationError("Cannot use your own referral code")
            except CodeValidationError:
                pass  # format validated earlier; deeper check will happen in service
        return attrs

    def create(self, validated_data):
        referral_code = validated_data['referral_code']
        referred_user = self.context['referred_user']
        request_meta = self.context.get('request_meta', {})
        service = ReferralRelationshipService()
        try:
            relationship = service.register_with_code(referral_code, referred_user, request_meta)
        except RelationshipError as e:
            raise serializers.ValidationError(str(e))
        return relationship


class ReferralRelationshipSerializer(serializers.ModelSerializer):
    referrer = serializers.PrimaryKeyRelatedField(read_only=True)
    referred_user = serializers.PrimaryKeyRelatedField(read_only=True)
    referral_code_used = serializers.CharField(source='referral_code_used.code', read_only=True)

    class Meta:
        model = ReferralRelationship
        fields = [
            'id',
            'referrer',
            'referred_user',
            'referral_code_used',
            'status',
            'user_verified_at',
            'first_payment_at',
            'first_payment_amount',
            'registration_ip',
            'registration_device_type',
            'days_to_verify',
            'days_to_first_payment',
            'referrer_rewarded_at',
            'referred_user_rewarded_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields
