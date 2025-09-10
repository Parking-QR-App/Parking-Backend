from rest_framework import serializers
from .models import User, BlacklistedAccessToken, UserDevice
from django.utils.timezone import now

class BaseUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'user_id', 'phone_number', 'email', 'first_name', 'last_name',
            'user_name', 'email_verified', 'phone_verified', 'is_active',
            'call_balance', 'address', 'license_plate_number', 'vehicle_type',
            'vehicle_model', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user_id', 'email_verified', 'phone_verified', 
                          'created_at', 'updated_at', 'is_active']

class AdminUserSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = BaseUserSerializer.Meta.fields + [
            'is_staff', 'is_superuser', 'last_login', 'otp', 'otp_expiry',
            'email_otp', 'email_otp_expiry'
        ]
        read_only_fields = BaseUserSerializer.Meta.read_only_fields + [
            'last_login', 'otp', 'otp_expiry', 'email_otp', 'email_otp_expiry'
        ]

class UserCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'phone_number',
            'email',
            'first_name',
            'last_name',
            'password'  # Special handling needed
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

class BlacklistedAccessTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlacklistedAccessToken
        fields = ['id', 'token', 'created_at']

class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    
    def validate_email(self, value):
        
        return value.lower()

class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)
    device_type = serializers.ChoiceField(
        choices=UserDevice.DEVICE_TYPES,
        required=False
    )
    os_version = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        email = attrs['email'].lower()
        otp = attrs['otp']
        
        user = User.objects.filter(
            email=email,
            email_otp=otp,
            email_otp_expiry__gt=now()
        ).first()

        if not user:
            raise serializers.ValidationError("Invalid OTP or OTP expired.")

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


class FlexibleUpdateUserInfoSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=30, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=30, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    license_plate_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    vehicle_type = serializers.CharField(max_length=50, required=False, allow_blank=True)
    vehicle_model = serializers.CharField(max_length=50, required=False, allow_blank=True)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            if value is not None:  # Update even if empty string
                setattr(instance, attr, value)
        instance.save()
        return instance