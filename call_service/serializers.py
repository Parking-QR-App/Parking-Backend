from rest_framework import serializers
from .models import CallRecord, CallEventLog
from decimal import Decimal

class CallRecordSerializer(serializers.ModelSerializer):
    inviter_name = serializers.CharField(source='inviter.get_full_name', read_only=True)
    invitee_name = serializers.CharField(source='invitee.get_full_name', read_only=True)
    inviter_rating = serializers.FloatField(read_only=True)
    invitee_rating = serializers.FloatField(read_only=True)
    total_duration = serializers.FloatField(read_only=True)
    answer_time = serializers.FloatField(read_only=True)
    
    class Meta:
        model = CallRecord
        fields = [
            'call_id', 'inviter', 'inviter_name', 'invitee', 'invitee_name',
            'call_type', 'state', 'duration', 'total_duration', 'answer_time',
            'initiated_at', 'ringing_at', 'accepted_at', 'rejected_at', 'ended_at',
            'was_connected', 'call_quality_rating', 'inviter_rating', 'invitee_rating',
            'ring_duration', 'response_time', 'deduction_status',
            'deducted_from_bonus', 'deducted_from_base', 'created_at'
        ]
        read_only_fields = [
            'call_id', 'inviter', 'invitee', 'state', 'duration', 'initiated_at',
            'ringing_at', 'accepted_at', 'rejected_at', 'ended_at', 'was_connected',
            'call_quality_rating', 'ring_duration', 'response_time', 'deduction_status',
            'deducted_from_bonus', 'deducted_from_base', 'created_at'
        ]

class CallRatingSerializer(serializers.Serializer):
    call_id = serializers.CharField(max_length=100)
    rating = serializers.FloatField(min_value=1.0, max_value=5.0)
    feedback = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_rating(self, value):
        """Validate rating is within acceptable range"""
        if value < 1.0 or value > 5.0:
            raise serializers.ValidationError("Rating must be between 1.0 and 5.0")
        return round(value, 1)  # Round to 1 decimal place

class CallEventLogSerializer(serializers.ModelSerializer):
    triggered_by_name = serializers.CharField(source='triggered_by.get_full_name', read_only=True)
    timestamp = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S')
    
    class Meta:
        model = CallEventLog
        fields = [
            'id', 'event_type', 'event_data', 'timestamp', 'triggered_by', 
            'triggered_by_name', 'ip_address'
        ]
        read_only_fields = ['id', 'timestamp']

class CallAnalyticsSerializer(serializers.Serializer):
    total_calls = serializers.IntegerField(default=0)
    outgoing_calls = serializers.IntegerField(default=0)
    incoming_calls = serializers.IntegerField(default=0)
    connected_calls = serializers.IntegerField(default=0)
    total_duration = serializers.FloatField(default=0.0)
    average_duration = serializers.FloatField(default=0.0)
    answer_rate = serializers.FloatField(default=0.0)
    average_answer_time = serializers.FloatField(default=0.0)
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    bonus_balance_used = serializers.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    base_balance_used = serializers.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

class CallDetailSerializer(serializers.ModelSerializer):
    inviter_name = serializers.CharField(source='inviter.get_full_name', read_only=True)
    invitee_name = serializers.CharField(source='invitee.get_full_name', read_only=True)
    inviter_email = serializers.CharField(source='inviter.email', read_only=True)
    invitee_email = serializers.CharField(source='invitee.email', read_only=True)
    event_logs = CallEventLogSerializer(many=True, read_only=True)
    
    class Meta:
        model = CallRecord
        fields = [
            'call_id', 'inviter', 'inviter_name', 'inviter_email', 
            'invitee', 'invitee_name', 'invitee_email', 'call_type', 
            'state', 'duration', 'initiated_at', 'ringing_at', 'accepted_at',
            'rejected_at', 'ended_at', 'was_connected', 'call_quality_rating',
            'inviter_rating', 'invitee_rating', 'inviter_feedback', 'invitee_feedback',
            'ring_duration', 'response_time', 'deduction_status', 'deducted_from_bonus',
            'deducted_from_base', 'inviter_ip', 'invitee_ip', 'inviter_device',
            'invitee_device', 'event_logs', 'created_at', 'updated_at'
        ]