# auth_service/services/registration_service.py
import random
from django.utils import timezone
from ..models import User
from ..utils import send_otp_email
from .firestore_service import create_user_in_firestore

class RegistrationService:
    @staticmethod
    def register_user(email: str):
        email = email.lower()  # Normalize email
        otp = str(random.randint(100000, 999999))
        
        try:
            user = User.objects.get(email=email)
            user.email_otp = otp
            user.email_otp_expiry = timezone.now() + timezone.timedelta(minutes=10)
            user.save()
            user_created = False
        except User.DoesNotExist:
            # Create user in firestore first
            firebase_user_profile = create_user_in_firestore(email)
            
            # Create Django user
            user = User.objects.create(
                email=email,
                email_otp=otp,
                email_otp_expiry=timezone.now() + timezone.timedelta(minutes=10),
                user_id=firebase_user_profile.get('uid', f"user_{random.randint(1000000000, 9999999999)}"),
                user_name=firebase_user_profile.get('username', email.split('@')[0])
            )
            user_created = True

        # Send OTP email
        send_otp_email(email, otp, user.user_name)
        return user, user_created