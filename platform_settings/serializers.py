from rest_framework import serializers
from .models import PlatformSetting, UserCallBalance, BalanceResetLog

class PlatformSettingSerializer(serializers.ModelSerializer):
    value = serializers.SerializerMethodField()
    
    class Meta:
        model = PlatformSetting
        fields = ['id', 'key', 'display_name', 'description', 'category', 
                 'setting_type', 'value', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_value(self, obj):
        return obj.value

class PlatformSettingUpdateSerializer(serializers.Serializer):
    value = serializers.CharField(required=True)
    
    def validate(self, data):
        setting = self.context['setting']
        value = data['value']
        
        try:
            if setting.setting_type == 'boolean':
                if value.lower() in ['true', '1', 'yes']:
                    data['value'] = True
                elif value.lower() in ['false', '0', 'no']:
                    data['value'] = False
                else:
                    raise serializers.ValidationError("Boolean value must be true/false")
            
            elif setting.setting_type == 'integer':
                data['value'] = int(value)
            
            elif setting.setting_type == 'decimal':
                data['value'] = float(value)
            
        except (ValueError, TypeError):
            raise serializers.ValidationError(f"Invalid value for type {setting.setting_type}")
        
        return data

class UserCallBalanceSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_id = serializers.CharField(source='user.user_id', read_only=True)
    total_balance = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = UserCallBalance
        fields = ['id', 'user_id', 'user_email', 'base_balance', 'bonus_balance', 
                 'total_balance', 'last_reset', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

class BalanceResetLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = BalanceResetLog
        fields = ['id', 'user_email', 'reset_type', 'previous_balance', 
                 'new_balance', 'reset_amount', 'notes', 'created_at']
        read_only_fields = ['id', 'created_at']

class BulkBalanceUpdateSerializer(serializers.Serializer):
    user_ids = serializers.ListField(child=serializers.CharField())
    base_balance = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    bonus_balance = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    operation = serializers.ChoiceField(choices=['set', 'add', 'subtract'], default='set')
    notes = serializers.CharField(required=False)

class CronExecutionSerializer(serializers.Serializer):
    dry_run = serializers.BooleanField(default=False)
    force = serializers.BooleanField(default=False)