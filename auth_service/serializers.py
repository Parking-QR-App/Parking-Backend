from rest_framework import serializers
from .models import User, BlacklistedAccessToken, UserDevice
from django.utils.timezone import now

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'phone_number', 'email', 'first_name', 'last_name',
            'email_verified', 'created_at', 'updated_at', 'is_active', 'is_staff', 'otp', 'otp_expiry'
        ]


class BlacklistedAccessTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlacklistedAccessToken
        fields = ['id', 'token', 'created_at']

class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['phone_number']

    def validate_phone_number(self, value):
        # Just validate the phone number format if needed, no uniqueness check
        return value

class VerifyOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    otp = serializers.CharField(min_length=6, max_length=6)
    device_type = serializers.ChoiceField(
        choices=UserDevice.DEVICE_TYPES,
        required=False
    )
    os_version = serializers.CharField(required=False)

    def validate(self, attrs):
        user = User.objects.filter(
            phone_number=attrs['phone_number'],
            otp=attrs['otp'],
            otp_expiry__gt=now()
        ).first()

        if not user:
            raise serializers.ValidationError("Invalid OTP or OTP expired.")

        # Attach user to validated data
        attrs['user'] = user
        return attrs


class EmailOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, data):
        data['email'] = data['email'].lower()
        user = self.context['request'].user
        if not user:
            raise serializers.ValidationError("User not found.")
        return data

class VerifyEmailOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField()

    def validate(self, data):
        data['email'] = data['email'].lower()
        try:
            user = User.objects.get(email=data['email'])

            # Check if the email is already verified
            if user.email_verified:
                raise serializers.ValidationError("Email already verified.")

            # Validate OTP
            print(user.email_otp)
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