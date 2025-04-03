from rest_framework import serializers
from .models import User
from django.utils.timezone import now
from .utils import generate_otp
from django.utils import timezone

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'phone_number', 'email', 'email_verified']

class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['phone_number']

    def validate_phone_number(self, value):
        # Just validate the phone number format if needed, no uniqueness check
        return value

class VerifyOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    otp = serializers.CharField()
    fcm_token = serializers.CharField(required=False, allow_blank=True)  # Optional
    device_type = serializers.ChoiceField(choices=["android", "ios"], required=False)  # Optional

    def validate(self, data):
        errors = {}

        try:
            user = User.objects.get(phone_number=data['phone_number'], otp=data['otp'])

            if user.otp_expiry < now():
                errors["otp"] = "OTP has expired."
                raise serializers.ValidationError(errors)

            return {
                "user": user,
                "fcm_token": data.get("fcm_token"),
                "device_type": data.get("device_type"),
            }

        except User.DoesNotExist:
            errors["otp"] = "Invalid OTP."
            raise serializers.ValidationError(errors)


class EmailOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, data):
        user = self.context['request'].user
        if not user:
            raise serializers.ValidationError("User not found.")
        return data

class VerifyEmailOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField()

    def validate(self, data):
        try:
            user = User.objects.get(email=data['email'])

            # Check if the email is already verified
            if user.email_verified:
                raise serializers.ValidationError("Email already verified.")

            # Validate OTP
            if user.email_otp != data['otp']:
                raise serializers.ValidationError("Invalid OTP.")

            # Check if OTP is expired
            if user.email_otp_expiry < now():
                raise serializers.ValidationError("OTP expired.")

            # Mark email as verified
            user.email_verified = True
            user.email_otp = None
            user.email_otp_expiry = None
            user.save()

            return user

        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")


class UpdateUserInfoSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=50, required=True)
    last_name = serializers.CharField(max_length=50, required=True)

    def update(self, instance, validated_data):
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.save()
        return instance