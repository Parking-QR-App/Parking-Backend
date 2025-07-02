from rest_framework import serializers
from ...models.notification import Notification

class NotificationCreateSerializer(serializers.Serializer):
    receiver_id = serializers.CharField()
    title = serializers.CharField(max_length=100)
    message = serializers.CharField()
    metadata = serializers.JSONField(required=False)
    idempotency_key = serializers.UUIDField(required=False)

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'type', 'title', 'message', 'is_read', 'created_at']