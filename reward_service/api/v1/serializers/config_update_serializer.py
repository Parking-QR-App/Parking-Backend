from rest_framework import serializers
from ....models import ReferralLimit


class ReferralLimitSerializer(serializers.ModelSerializer):
    can_refer_daily = serializers.SerializerMethodField()
    can_refer_weekly = serializers.SerializerMethodField()
    can_refer_monthly = serializers.SerializerMethodField()
    can_refer_total = serializers.SerializerMethodField()
    success_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = ReferralLimit
        fields = [
            'user',
            'daily_limit',
            'weekly_limit',
            'monthly_limit',
            'total_limit',
            'daily_used',
            'weekly_used',
            'monthly_used',
            'total_used',
            'is_unlimited',
            'is_suspended',
            'suspension_reason',
            'successful_referrals',
            'verified_referrals',
            'paying_referrals',
            'can_refer_daily',
            'can_refer_weekly',
            'can_refer_monthly',
            'can_refer_total',
            'success_rate',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_can_refer_daily(self, obj):
        return obj.can_refer('daily')

    def get_can_refer_weekly(self, obj):
        return obj.can_refer('weekly')

    def get_can_refer_monthly(self, obj):
        return obj.can_refer('monthly')

    def get_can_refer_total(self, obj):
        return obj.can_refer('total')
