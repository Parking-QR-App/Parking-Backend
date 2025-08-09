from rest_framework import serializers
from django.contrib.auth import get_user_model
from ....services.admin_service import AdminReferralService
from ....services.exceptions import AdminOperationError

User = get_user_model()


class AdminSetLimitsSerializer(serializers.Serializer):
    user_id = serializers.CharField()
    daily = serializers.IntegerField(required=False, min_value=0)
    weekly = serializers.IntegerField(required=False, min_value=0)
    monthly = serializers.IntegerField(required=False, min_value=0)
    total = serializers.IntegerField(required=False, min_value=0)
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate_user_id(self, value):
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Target user not found")
        self.context['user'] = user
        return value

    def validate(self, attrs):
        if not any(k in attrs for k in ('daily', 'weekly', 'monthly', 'total')):
            raise serializers.ValidationError("At least one limit must be provided to set")
        return attrs

    def save(self, **kwargs):
        user = self.context['user']
        try:
            limit = AdminReferralService.set_limits(
                user,
                daily=self.validated_data.get('daily'),
                weekly=self.validated_data.get('weekly'),
                monthly=self.validated_data.get('monthly'),
                total=self.validated_data.get('total'),
                actor=self.context.get('actor'),
                reason=self.validated_data.get('reason', '')
            )
        except AdminOperationError as e:
            raise serializers.ValidationError(str(e))
        return limit


class AdminAdjustLimitsSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    delta_daily = serializers.IntegerField(required=False)
    delta_weekly = serializers.IntegerField(required=False)
    delta_monthly = serializers.IntegerField(required=False)
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate_user_id(self, value):
        try:
            user = User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Target user not found")
        self.context['user'] = user
        return value

    def validate(self, attrs):
        if not any(k in attrs for k in ('delta_daily', 'delta_weekly', 'delta_monthly')):
            raise serializers.ValidationError("At least one delta must be provided")
        return attrs

    def save(self, **kwargs):
        user = self.context['user']
        try:
            limit = AdminReferralService.adjust_limits(
                user,
                delta_daily=self.validated_data.get('delta_daily', 0),
                delta_weekly=self.validated_data.get('delta_weekly', 0),
                delta_monthly=self.validated_data.get('delta_monthly', 0),
                actor=self.context.get('actor'),
                reason=self.validated_data.get('reason', '')
            )
        except AdminOperationError as e:
            raise serializers.ValidationError(str(e))
        return limit
