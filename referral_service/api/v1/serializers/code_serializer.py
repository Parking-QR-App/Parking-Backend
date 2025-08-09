from rest_framework import serializers
from django.contrib.auth import get_user_model
from ....models import ReferralCode
from ....services.referral_code_service import ReferralCodeService
from ....services.exceptions import CodeValidationError

User = get_user_model()

class ReferralCodeSerializer(serializers.ModelSerializer):
    """
    Read-only representation of a referral code, including validity and conversion rate.
    """
    is_valid = serializers.BooleanField(read_only=True)
    conversion_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = ReferralCode
        fields = [
            'id',
            'code',
            'code_type',
            'status',
            'owner',
            'usage_count',
            'usage_limit',
            'valid_from',
            'valid_until',
            'is_valid',
            'conversion_rate',
            'total_registrations',
            'total_verified_users',
            'total_paying_users',
            'total_revenue_generated',
            'notes',
            'created_by_admin',
            'created_at',
            'updated_at',
            'last_used_at',
        ]
        read_only_fields = fields

class UserReferralCodeCreateSerializer(serializers.Serializer):
    """
    Create or fetch a user-type referral code if eligible.
    """
    user_id = serializers.CharField(write_only=True)
    referral_code = serializers.CharField(read_only=True)

    def validate_user_id(self, value):
        try:
            user = User.objects.get(user_id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User not found")
        self.context['user'] = user
        return value

    def create(self, validated_data):
        user = self.context['user']
        code_obj = ReferralCodeService.generate_for_user_if_eligible(user)
        if not code_obj:
            raise serializers.ValidationError("User not eligible for referral code yet")
        return {'referral_code': code_obj.code}


class CreateCampaignCodeSerializer(serializers.Serializer):
    """
    Admin creates a single campaign-type referral code (no external campaign model).
    """
    prefix = serializers.CharField(required=False, allow_blank=True, max_length=5)
    note = serializers.CharField(required=False, allow_blank=True)
    created_by = serializers.CharField(write_only=True)

    code = serializers.CharField(read_only=True)
    code_id = serializers.UUIDField(read_only=True)

    def validate_created_by(self, value):
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Creator user not found")
        self.context['created_by'] = user
        return value

    def create(self, validated_data):
        creator = self.context['created_by']
        prefix = validated_data.get('prefix', '')
        note = validated_data.get('note', '')

        try:
            code_obj = ReferralCodeService.create_campaign_code(
                created_by=creator,
                prefix=prefix,
                note=note
            )
        except CodeValidationError as e:
            raise serializers.ValidationError(str(e))

        return {'code': code_obj.code, 'code_id': code_obj.id}
