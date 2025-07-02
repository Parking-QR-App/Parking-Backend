from django.urls import path
from .views import (
    GenerateUserQRCodeView, GenerateAdminQRCodeView, ScanQRCodeView,
    RegisterQRCodeView, QRCodeAnalyticsView, AdminQRCodeAnalyticsView, ControlQRCodeView
)

urlpatterns = [
    path("generate-qr/", GenerateUserQRCodeView.as_view(), name="generate_qr"),
    path("admin/generate-qr/", GenerateAdminQRCodeView.as_view(), name="admin_generate_qr"),
    path("scan-qr/<str:hashed_qr_id>/", ScanQRCodeView.as_view(), name="scan_qr"),
    path("register-qr/<str:hashed_qr_id>/", RegisterQRCodeView.as_view(), name="register_qr"),
    path("qr-analytics/<str:hashed_qr_id>/", QRCodeAnalyticsView.as_view(), name="qr_analytics"),
    path("admin/qr-analytics/", AdminQRCodeAnalyticsView.as_view(), name="admin_qr_analytics"),
    path("control-qr/", ControlQRCodeView.as_view(), name="control-qr")
]
