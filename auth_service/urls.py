from django.urls import path
from .views import RegisterView, VerifyOTPView, SendEmailOTPView, VerifyEmailOTPView, UpdateUserInfoView, LogoutView, CustomTokenRefreshView, ScanCarPlateView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('send-email-otp/', SendEmailOTPView.as_view(), name='send-email-otp'),
    path('verify-email-otp/', VerifyEmailOTPView.as_view(), name='verify-email-otp'),
    path('update-info/', UpdateUserInfoView.as_view(), name='update-info'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token-refresh/', CustomTokenRefreshView.as_view(), name='custom_token_refresh'),
    path('car-plate-scan/<str:car_plate_number>', ScanCarPlateView.as_view(), name='car-plate-scan'),
]
