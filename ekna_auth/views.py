from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework import status
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from .models import Users, OTP
from .utils import get_tokens_for_user, generate_otp, send_otp_email, send_password_email, generate_random_password
from datetime import timedelta


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            'username': user.username,
            'email': user.email,
        })
        
    permission_classes = [IsAuthenticated]
    def post(self, request):
        try:
            data = request.data
            user = request.user

            if 'username' in data:
                user.username = data['username']
            
            if 'email' in data:
                if Users.objects.filter(email=data['email']).exclude(id=user.id).exists():
                    return Response({'error': 'Email already exists'}, 
                                status=status.HTTP_400_BAD_REQUEST)
                user.email = data['email']
            
            if 'password' in data:
                user.set_password(data['password'])

            user.save()

            return Response({
                'message': 'Profile updated successfully',
                'user': {
                    'name': user.username,
                    'email': user.email,
                }
            })

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class RegisterUserView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        try:
            data = request.data
            username = data.get('username')
            email = data.get('email')
            password = data.get('password')

            if not all([username, email, password]):
                return Response({'error': 'Name, email, and password are required'}, 
                                status=status.HTTP_400_BAD_REQUEST)

            if Users.objects.filter(email=email).exists():
                return Response({'error': 'Email already exists'}, 
                                status=status.HTTP_400_BAD_REQUEST)
                
            user = Users.objects.create(
                email=email,
                username=username,
                password=make_password(password),
                last_login=timezone.now()
            )
            
            otp = generate_otp()
            
            OTP.objects.filter(user=user, is_verified=False).delete()
            OTP.objects.create(user=user, otp_code=otp)
            
            send_otp_email(user, otp)
            
            return Response({
                'message': 'User registered successfully and OTP Sent',
                'user': {
                    'name': user.username,
                    'email': user.email,
                },
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'error': str(e)}, 
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        otp_code = request.data['otp']
        email = request.data['email']
        
        try:
            user = Users.objects.get(email=email)
            otp = OTP.objects.get(
                user=user, 
                otp_code=otp_code, 
                is_verified=False,
                created_at__gte=timezone.now() - timedelta(minutes=15)  # OTP valid for 15 minutes
            )
            
            # Mark OTP as verified
            otp.is_verified = True
            otp.save()
            
            # Generate JWT tokens
            tokens = get_tokens_for_user(user)
            
            return Response({
                'message': 'User verified and logged in.',
                'user': {
                    'name': user.username,
                    'email': user.email,
                },
                'tokens': tokens
            }, status=status.HTTP_200_OK)
            
        except (Users.DoesNotExist, OTP.DoesNotExist):
            return Response({
                'error': 'Invalid OTP or email'
            }, status=status.HTTP_400_BAD_REQUEST)


class LoginUserView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        try:
            data = request.data
            email = data.get('email')
            password = data.get('password')

            if not all([email, password]):
                return Response({'error': 'Email and password are required'}, 
                                status=status.HTTP_400_BAD_REQUEST)

            user = Users.objects.filter(email=email).first()

            if not user or not user.check_password(password):
                return Response({'error': 'Invalid email or password'}, 
                                status=status.HTTP_401_UNAUTHORIZED)
                
            if OTP.objects.filter(user=user, is_verified=False).exists():
                otp = generate_otp()
            
                OTP.objects.filter(user=user, is_verified=False).delete()
                OTP.objects.create(user=user, otp_code=otp)
                
                send_otp_email(user, otp)
                
                return Response({
                    'error': 'User is not verified. OTP Sent',
                    'user': {
                        'name': user.username,
                        'email': user.email,
                    }
                }, status=status.HTTP_401_UNAUTHORIZED)
                
            tokens = get_tokens_for_user(user)
            
            user.last_login = timezone.now()
            user.save()
            
            return Response({
                'message': 'User logged in successfully',
                'user': {
                    'name': user.username,
                    'email': user.email,
                },
                'tokens': tokens
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class LogoutUserView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            return Response({'message': 'Logged out successfully'}, 
                            status=status.HTTP_200_OK)
        except TokenError:
            return Response({'error': 'Invalid token'}, 
                            status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RefreshTokenView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                access = token.access_token
                
                return Response({'access': str(access)}, 
                                status=status.HTTP_200_OK)
                
            return Response({'error': 'Token not found in request data or invalid token'}, 
                            status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class ForgetPasswordView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        """Send new password via email"""
        try:
            data = request.data
            email = data.get('email')

            if not email:
                return Response({'error': 'Email is required'}, 
                            status=status.HTTP_400_BAD_REQUEST)

            try:
                user = Users.objects.get(email=email)
            except Users.DoesNotExist:
                return Response({'error': 'User not found'}, 
                            status=status.HTTP_404_NOT_FOUND)

            # Generate new password
            new_password = generate_random_password()
            user.set_password(new_password)
            user.save()

            # Send email
            send_password_email(user, new_password)

            return Response({'message': 'New password sent to your email'})

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        