from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, VerifyOTPView, SendEmailOTPView, VerifyEmailOTPView, UpdateUserInfoView, LogoutView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('send-email-otp/', SendEmailOTPView.as_view(), name='send-email-otp'),
    path('verify-email-otp/', VerifyEmailOTPView.as_view(), name='verify-email-otp'),
    path('update-info/', UpdateUserInfoView.as_view(), name='update-info'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token-refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
