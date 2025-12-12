from django.core.mail import send_mail
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken 
import random
import string

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
    
def generate_otp():
    return str(random.randint(1000, 9999))

def generate_random_password(length=8):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for i in range(length))

def send_otp_email(user, otp):
    subject = 'EKNA - Registration OTP'
    message = f"""
        Dear {user.username},

        You have successfully generated OTP for EKNA Registration.

        OTP is valid for 15 mins.

        Do not share the OTP with anyone to avoid misuse of your account.

        The OTP is {otp}.

        If you have not done the activity please contact   "support team"   immediately.

        Best regards,
        EKNA Team
        """
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"Failed to send OTP email: {e}")
        
        
        
def send_password_email(user, new_password):
    subject = 'EKNA - Password Reset'
    message = f"""
        Dear {user.username},

        Your password has been reset successfully.

        Your new password: {new_password}

        Please login and change your password immediately for security reasons.

        Best regards,
        EKNA Team
        """
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as e:
        print(f"Failed to send password reset email: {e}")