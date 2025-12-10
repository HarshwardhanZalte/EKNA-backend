from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework import status
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from .models import Users

class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            'username': user.username,
            'email': user.email,
        })
        
        
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class RegisterUserView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        try:
            data = request.data
            username = data.get('name')
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

            tokens = get_tokens_for_user(user)
            
            return Response({
                'message': 'User registered successfully',
                'user': {
                    'name': user.username,
                    'email': user.email,
                },
                'tokens': tokens
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'error': str(e)}, 
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
        