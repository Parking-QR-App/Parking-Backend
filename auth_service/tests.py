from django.test import TestCase, RequestFactory
from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.utils.timezone import now
from .models import UserDevice
from .middleware import DeviceActivityMiddleware
from datetime import timedelta
from django.contrib.auth.models import AnonymousUser

User = get_user_model()

class TestDeviceMiddleware(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create(
            phone_number="+1234567890",
            user_id="test123",
            user_name="test_user"
        )
        self.device = UserDevice.objects.create(
            user=self.user,
            device_id="test-device-id",
            fcm_token="initial-fcm-token",
            device_type="android",
            last_active=now() - timedelta(days=1)
        )

    def test_middleware_updates_last_active_and_fcm_token(self):
        """Ensure middleware updates FCM token and last_active correctly"""
        request = self.factory.get(
            '/dummy-endpoint/',
            HTTP_X_DEVICE_ID="test-device-id",
            HTTP_X_FCM_TOKEN="updated-fcm-token"
        )
        request.user = self.user

        middleware = DeviceActivityMiddleware(lambda r: HttpResponse(status=200))
        response = middleware(request)

        self.device.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.device.fcm_token, "updated-fcm-token")
        self.assertTrue(self.device.last_active > now() - timedelta(minutes=1))


class TestDeviceMiddlewareEdgeCases(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create(
            phone_number="+1234567890",
            user_id="test-edgecase",
            user_name="edge_user"
        )
        self.device = UserDevice.objects.create(
            user=self.user,
            device_id="edge-device-id",
            fcm_token="edge-token",
            device_type="ios",
            last_active=now() - timedelta(hours=2)
        )

    def test_middleware_skips_without_device_id(self):
        """Ensure middleware skips when device ID is missing"""
        request = self.factory.get('/', HTTP_X_FCM_TOKEN="some-token")
        request.user = self.user

        middleware = DeviceActivityMiddleware(lambda r: HttpResponse(status=200))
        response = middleware(request)

        self.device.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.device.fcm_token, "edge-token")  # Unchanged
        self.assertTrue(self.device.last_active < now() - timedelta(minutes=1))

    def test_middleware_skips_for_unauthenticated_user(self):
        """Ensure middleware skips unauthenticated users"""
        request = self.factory.get(
            '/', 
            HTTP_X_DEVICE_ID="edge-device-id", 
            HTTP_X_FCM_TOKEN="unauth-token"
        )
        request.user = AnonymousUser()

        middleware = DeviceActivityMiddleware(lambda r: HttpResponse(status=200))
        response = middleware(request)

        self.device.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.device.fcm_token, "edge-token")  # Should not change
