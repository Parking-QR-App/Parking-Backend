from rest_framework import serializers
from .models import Call

class CallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Call
        fields = ['id', 'room_name', 'host', 'participants', 'started_at', 'ended_at', 'is_active']
