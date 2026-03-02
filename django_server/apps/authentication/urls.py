from django.urls import path
from .views import SignUpView, LoginView, LogoutView, UserProfileView, PasswordResetView

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='auth-signup'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('profile/', UserProfileView.as_view(), name='auth-profile'),
    path('password-reset/', PasswordResetView.as_view(), name='auth-password-reset'),
]
