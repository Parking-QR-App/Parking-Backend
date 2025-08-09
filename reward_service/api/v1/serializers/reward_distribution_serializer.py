from rest_framework import serializers
from django.contrib.auth import get_user_model
from ....services.referral_code_service import ReferralCodeService
from ....services.exceptions import CodeValidationError

User = get_user_model()


class ReferralCodeBatchCreateSerializer(serializers.Serializer):
    """
    Admin bulk-creates campaign-type referral codes (no campaign/batch model).
    """
    prefix = serializers.CharField(required=False, allow_blank=True, max_length=5)
    quantity = serializers.IntegerField(min_value=1)
    created_by = serializers.CharField(write_only=True)
    note = serializers.CharField(required=False, allow_blank=True)

    codes = serializers.ListField(child=serializers.CharField(), read_only=True)

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
        quantity = validated_data['quantity']
        note = validated_data.get('note', '')

        try:
            codes = ReferralCodeService.bulk_create_campaign_codes(
                created_by=creator,
                prefix=prefix,
                quantity=quantity,
                note=note
            )
        except CodeValidationError as e:
            raise serializers.ValidationError(str(e))
        except Exception as e:
            raise serializers.ValidationError(f"Failed to generate codes: {str(e)}")

        return {'codes': codes}
