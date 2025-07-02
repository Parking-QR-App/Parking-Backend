from django.urls import path, include

urlpatterns = [
    path('v1/', include('alert_service.api.v1.urls')),
    # Future versions would go here:
    # path('v2/', include('alert_service.api.v2.urls')),
]