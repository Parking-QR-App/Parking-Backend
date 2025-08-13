import os
import json
import logging
import firebase_admin
from firebase_admin import messaging, credentials
from firebase_admin.exceptions import FirebaseError
from django.conf import settings
from .auth_client import AuthServiceClient

logger = logging.getLogger(__name__)

def get_firebase_cred():
    """Return a firebase_admin credentials object from either env var or local file."""
    if os.environ.get("FIREBASE_CREDENTIALS"):
        # Load from environment variable in production
        firebase_creds_dict = json.loads(os.environ["FIREBASE_CREDENTIALS"])
        return credentials.Certificate(firebase_creds_dict)
    else:
        # Load from local file in development
        cred_path = os.path.join(settings.BASE_DIR, 'zegocloud-3d68b-firebase-adminsdk-fbsvc-9a16f37574.json')
        return credentials.Certificate(cred_path)
    
class FCMClient:
    @classmethod
    def initialize(cls):
        """Initialize Firebase app if not already initialized"""
        if not firebase_admin._apps:
            try:
                # Use absolute path to avoid path issues in production
                # cred_path = os.path.join(settings.BASE_DIR, 'zegocloud-3d68b-firebase-adminsdk-fbsvc-9a16f37574.json')
                # cred = credentials.Certificate(cred_path)
                cred = get_firebase_cred()
                firebase_admin.initialize_app(cred)
                logger.info("[FCM] Firebase app initialized successfully.")
            except Exception as e:
                logger.error(f"[FCM] Initialization failed: {str(e)}")
                raise

    @staticmethod
    def send(user_id, notification_id, title, body, data):
        """
        Send FCM notification to a React Native device with deep linking support.
        Params:
            - user_id: ID of the callee or receiver
            - notification_id: Notification DB ID to allow frontend deep linking
            - title: Notification title
            - body: Notification body
            - data: Extra metadata (should include type, etc.)
        """
        print("SENDER")  # Debug
        try:
            device = AuthServiceClient.get_user_device(user_id)
            if not device or not device.fcm_token:
                logger.warning(f"[FCM] No FCM token found for user {user_id}")
                return False

            fcm_token = device.fcm_token
            logger.debug(f"[FCM] Sending to token: {fcm_token}")

            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                token=fcm_token,
                data={
                    **data,
                    "notificationId": str(notification_id),
                    "url": f"myapp://alert/v1/notifications/{notification_id}",  # Deep link
                    "title": title,
                    "body": body,
                    "route": "Alerts",               # React Native top-level route
                    "screen": "AlertDetail",         # React Native screen
                    "params": json.dumps({
                        "notificationId": str(notification_id),
                        "alertType": data.get("type", "general")
                    })
                },
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        channel_id="zego_audio_call",
                        sound="zego_incoming",
                        click_action="OPEN_NOTIFICATION"
                    )
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            alert=messaging.ApsAlert(
                                title=title,
                                body=body
                            ),
                            sound="zego_incoming",
                            category="OPEN_NOTIFICATION"
                        )
                    )
                )
            )

            response = messaging.send(message)
            print(f"✅ FCM sent. Message ID: {response}")
            logger.info(f"[FCM] Sent notification {notification_id}. FCM Message ID: {response}")
            return True

        except FirebaseError as e:
            print("❌ FirebaseError:", str(e))
            logger.error(f"[FCM] FirebaseError: {str(e)}")
            return False

        except Exception as ex:
            print("❌ Unexpected FCM error:", str(ex))
            logger.exception(f"[FCM] Unexpected error while sending FCM: {str(ex)}")
            return False
