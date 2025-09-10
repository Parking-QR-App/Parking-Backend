from django.contrib import admin
from django.utils.html import format_html
from .models import PlatformSetting, UserCallBalance, BalanceResetLog

@admin.register(PlatformSetting)
class PlatformSettingAdmin(admin.ModelAdmin):
    list_display = ['key', 'display_name', 'category', 'value_display', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['key', 'display_name']
    
    def value_display(self, obj):
        value = obj.value
        if obj.setting_type == 'boolean':
            color = 'green' if value else 'red'
            text = 'Yes' if value else 'No'
            return format_html('<span style="color: {};">{}</span>', color, text)
        return value
    value_display.short_description = 'Value'

@admin.register(UserCallBalance)
class UserCallBalanceAdmin(admin.ModelAdmin):
    list_display = ['user_email', 'base_balance', 'bonus_balance', 'total_balance', 'last_reset']
    search_fields = ['user__email', 'user__user_id']
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
    
    def total_balance(self, obj):
        return obj.total_balance
    total_balance.short_description = 'Total Calls'

@admin.register(BalanceResetLog)
class BalanceResetLogAdmin(admin.ModelAdmin):
    list_display = ['user_email', 'reset_type', 'previous_balance', 'new_balance', 'created_at']
    list_filter = ['reset_type', 'created_at']
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'