# auth_service/utils.py
import random
import os
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(user_email, otp_code, user_name=None):
    try:
        # Render the HTML email template
        context = {
            'user_name': user_name or 'User',
            'otp_code': otp_code,
        }

        # Render the HTML email template
        template_path = os.path.join(settings.BASE_DIR, 'email_templates/otp_email.html')
        html_message = render_to_string(template_path, context)

        # Strip the HTML to create a plain-text version
        plain_message = strip_tags(html_message)
        
        # Send the email
        email = EmailMessage(
            subject='Your OTP Code',
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user_email],
        )
        email.content_subtype = 'html'
        email.send()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def send_welcome_email(user_email, user_name):
    try:
        context = {
            'user_name': user_name,
        }
        
        # Render the HTML email template
        template_path = os.path.join(settings.BASE_DIR, 'email_templates/otp_email.html')
        html_message = render_to_string(template_path, context)
        
        plain_message = strip_tags(html_message)
        
        email = EmailMessage(
            subject='Welcome to Our Service!',
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user_email],
        )
        email.content_subtype = 'html'
        email.send()
        return True
    except Exception as e:
        print(f"Failed to send welcome email: {e}")
        return False