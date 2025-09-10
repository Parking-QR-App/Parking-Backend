from rest_framework import serializers
from ...models import ReferralCode, ReferralRelationship, ReferralSettings
from django.utils import timezone
from decimal import Decimal

class ReferralCodeSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    
    class Meta:
        model = ReferralCode
        fields = [
            'id', 'code', 'code_type', 'status', 'owner', 'owner_email',
            'usage_count', 'max_usage', 'valid_from', 'valid_until',
            'reward_calls', 'is_valid', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'usage_count']

class ReferralRelationshipSerializer(serializers.ModelSerializer):
    referrer_email = serializers.EmailField(source='referrer.email', read_only=True)
    referred_user_email = serializers.EmailField(source='referred_user.email', read_only=True)
    referral_code_str = serializers.CharField(source='referral_code.code', read_only=True)
    
    class Meta:
        model = ReferralRelationship
        fields = [
            'id', 'referrer', 'referrer_email', 'referred_user', 'referred_user_email',
            'referral_code', 'referral_code_str', 'status', 'reward_calls_given',
            'reward_given_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

class ReferralSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferralSettings
        fields = ['id', 'key', 'value', 'description', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class CreateCampaignCodeSerializer(serializers.Serializer):
    code = serializers.CharField(required=False, max_length=20)
    status = serializers.ChoiceField(choices=ReferralCode.STATUS_CHOICES, default='active')
    max_usage = serializers.IntegerField(min_value=Decimal('0.00'), default=0)
    valid_from = serializers.DateTimeField(default=timezone.now)
    valid_until = serializers.DateTimeField(required=False, allow_null=True)
    reward_calls = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.00'), default=5.00)

class ApplyReferralCodeSerializer(serializers.Serializer):
    referral_code = serializers.CharField(max_length=20)

class AdminSetLimitsSerializer(serializers.Serializer):
    user_id = serializers.CharField()
    max_daily_referrals = serializers.IntegerField(min_value=Decimal('0.00'), default=10)
    max_total_referrals = serializers.IntegerField(min_value=Decimal('0.00'), default=100)