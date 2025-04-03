import random
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import os
from django.conf import settings

def generate_otp():
    return str(random.randint(100000, 999999))

# def send_email_verification(user):
#     verification_link = f"{settings.FRONTEND_URL}/verify-email/{user.user_id}/"
#     send_mail(
#         "Verify Your Email",
#         f"Click the link to verify: {verification_link}",
#         settings.EMAIL_HOST_USER,
#         [user.email],
#         fail_silently=False,
#     )

def send_otp_email(user_email, otp_code):
    # Render the HTML email template
    template_path = os.path.join(settings.BASE_DIR, 'email_templates/otp_email.html')
    html_message = render_to_string(template_path, {
        'user_name': 'User',
        'otp_code': otp_code,
    })
    
    # Strip the HTML to create a plain-text version
    plain_message = strip_tags(html_message)
    
    # Send the email
    email = EmailMessage(
        subject='Your OTP Code',
        body=plain_message,
        from_email='your_email@gmail.com',  # or use a variable if you prefer
        to=[user_email],
    )
    email.content_subtype = 'html'  # Important to send HTML email
    email.send()