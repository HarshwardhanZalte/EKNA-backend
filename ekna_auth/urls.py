from django.urls import path
from .views import UserProfileView, RegisterUserView, LoginUserView, LogoutUserView, RefreshTokenView

urlpatterns = [
    # APP URLS
    path('profile/', UserProfileView.as_view(), name='user_profile'),
    path('register/', RegisterUserView.as_view(), name='register_user'),
    path('login/', LoginUserView.as_view(), name='login_user'),
    path('logout/', LogoutUserView.as_view(), name='logout_user'),
    path('refresh-token/', RefreshTokenView.as_view(), name='refresh_token'),
]