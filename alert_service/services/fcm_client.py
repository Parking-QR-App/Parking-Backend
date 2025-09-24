import os
import json
import logging
import firebase_admin
from firebase_admin import messaging, credentials
from firebase_admin.exceptions import FirebaseError
from django.conf import settings
from .auth_client import AuthServiceClient

# Import proper API exceptions
from shared.utils.api_exceptions import (
    ValidationException,
    ServiceUnavailableException,
    NotFoundException,
    AuthenticationException
)

logger = logging.getLogger(__name__)

def get_firebase_cred():
    """Return a firebase_admin credentials object from either env var or local file."""
    try:
        if os.environ.get("FIREBASE_CREDENTIALS"):
            # Load from environment variable in production
            firebase_creds_json = os.environ["FIREBASE_CREDENTIALS"]
            if not firebase_creds_json.strip():
                raise ValidationException(
                    detail="Invalid Firebase credentials",
                    context={'credentials': 'FIREBASE_CREDENTIALS environment variable is empty'}
                )
            
            try:
                firebase_creds_dict = json.loads(firebase_creds_json)
            except json.JSONDecodeError as e:
                raise ValidationException(
                    detail="Invalid Firebase credentials format",
                    context={'credentials': f'JSON decode error: {str(e)}'}
                )
            
            return credentials.Certificate(firebase_creds_dict)
        else:
            # Load from local file in development
            cred_path = os.path.join(settings.BASE_DIR, 'zegocloud-3d68b-firebase-adminsdk-fbsvc-9a16f37574.json')
            
            if not os.path.exists(cred_path):
                raise ServiceUnavailableException(
                    detail="Firebase credentials file not found",
                    context={
                        'file_path': cred_path,
                        'environment': 'development'
                    }
                )
            
            return credentials.Certificate(cred_path)
            
    except ValidationException:
        raise
    except ServiceUnavailableException:
        raise
    except Exception as e:
        logger.error(f"Failed to load Firebase credentials: {str(e)}")
        raise ServiceUnavailableException(
            detail="Firebase credential service unavailable",
            context={'error': str(e)}
        )

class FCMClient:
    @classmethod
    def initialize(cls):
        """Initialize Firebase app if not already initialized"""
        if firebase_admin._apps:
            logger.debug("Firebase app already initialized")
            return
        
        try:
            cred = get_firebase_cred()
            firebase_admin.initialize_app(cred)
            logger.info("Firebase app initialized successfully")
            
        except ValidationException:
            raise
        except ServiceUnavailableException:
            raise
        except FirebaseError as e:
            logger.error(f"Firebase initialization failed: {str(e)}")
            raise ServiceUnavailableException(
                detail="Firebase service initialization failed",
                context={'service': 'Firebase Admin SDK', 'error': str(e)}
            )
        except Exception as e:
            logger.error(f"Unexpected error initializing Firebase: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Firebase initialization service unavailable"
            )

    @staticmethod
    def send(user_id, notification_id, title, body, data):
        """
        Send FCM notification to a React Native device with deep linking support.
        
        Args:
            user_id: ID of the callee or receiver
            notification_id: Notification DB ID to allow frontend deep linking
            title: Notification title
            body: Notification body
            data: Extra metadata (should include type, etc.)
            
        Raises:
            ValidationException: Invalid input parameters
            NotFoundException: User or device not found
            ServiceUnavailableException: FCM service issues
        """
        # Input validation
        if not user_id:
            raise ValidationException(
                detail="User ID is required",
                context={'user_id': 'User ID cannot be empty'}
            )
        
        if not notification_id:
            raise ValidationException(
                detail="Notification ID is required",
                context={'notification_id': 'Notification ID cannot be empty'}
            )
        
        if not title or not isinstance(title, str):
            raise ValidationException(
                detail="Invalid notification title",
                context={'title': 'Title must be a non-empty string'}
            )
        
        if not body or not isinstance(body, str):
            raise ValidationException(
                detail="Invalid notification body",
                context={'body': 'Body must be a non-empty string'}
            )
        
        if not data or not isinstance(data, dict):
            raise ValidationException(
                detail="Invalid notification data",
                context={'data': 'Data must be a dictionary'}
            )

        try:
            # Ensure Firebase is initialized
            FCMClient.initialize()
            
            # Get user device
            try:
                device = AuthServiceClient.get_user_device(user_id)
            except Exception as e:
                logger.error(f"Failed to get user device for {user_id}: {str(e)}")
                raise ServiceUnavailableException(
                    detail="User device service unavailable",
                    context={'user_id': str(user_id)}
                )
            
            if not device:
                raise NotFoundException(
                    detail="User device not found",
                    context={
                        'user_id': str(user_id),
                        'reason': 'No registered device for this user'
                    }
                )
            
            if not device.fcm_token:
                raise NotFoundException(
                    detail="FCM token not found",
                    context={
                        'user_id': str(user_id),
                        'reason': 'No FCM token registered for user device'
                    }
                )

            fcm_token = device.fcm_token
            logger.debug(f"Sending FCM notification to user {user_id}")

            # Prepare notification data
            notification_data = {
                **data,
                "notificationId": str(notification_id),
                "url": f"myapp://alert/v1/notifications/{notification_id}",
                "title": title,
                "body": body,
                "route": "Alerts",
                "screen": "AlertDetail",
                "params": json.dumps({
                    "notificationId": str(notification_id),
                    "alertType": data.get("type", "general")
                })
            }

            # Create FCM message
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                token=fcm_token,
                data=notification_data,
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

            # Send the message
            try:
                response = messaging.send(message)
                logger.info(f"FCM notification sent successfully. Message ID: {response}")
                return response  # Return message ID instead of boolean
                
            except messaging.UnregisteredError:
                logger.warning(f"FCM token unregistered for user {user_id}")
                raise NotFoundException(
                    detail="FCM token no longer valid",
                    context={
                        'user_id': str(user_id),
                        'fcm_token': fcm_token[:20] + "...",  # Partial token for debugging
                        'reason': 'Token unregistered or expired'
                    }
                )
            except messaging.SenderIdMismatchError:
                logger.error(f"FCM sender ID mismatch for user {user_id}")
                raise AuthenticationException(
                    detail="FCM authentication error",
                    context={'service': 'FCM', 'reason': 'Sender ID mismatch'}
                )
            except messaging.QuotaExceededError:
                logger.error("FCM quota exceeded")
                raise ServiceUnavailableException(
                    detail="FCM service quota exceeded",
                    context={'service': 'FCM', 'reason': 'Rate limit exceeded'}
                )
            except FirebaseError as e:
                logger.error(f"Firebase error sending FCM: {str(e)}")
                raise ServiceUnavailableException(
                    detail="FCM service error",
                    context={'service': 'Firebase FCM', 'error': str(e)}
                )

        except ValidationException:
            raise
        except NotFoundException:
            raise
        except AuthenticationException:
            raise
        except ServiceUnavailableException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending FCM notification: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="FCM notification service temporarily unavailable",
                context={
                    'user_message': 'Unable to send notification. Please try again.',
                    'user_id': str(user_id)
                }
            )
    
    @staticmethod
    def send_bulk(user_notifications):
        """
        Send FCM notifications to multiple users in bulk.
        
        Args:
            user_notifications: List of dicts with keys: user_id, notification_id, title, body, data
            
        Returns:
            Dict with success_count, failed_count, and results
        """
        if not user_notifications or not isinstance(user_notifications, list):
            raise ValidationException(
                detail="Invalid bulk notification data",
                context={'user_notifications': 'Must be a non-empty list'}
            )
        
        results = {
            'success_count': 0,
            'failed_count': 0,
            'results': []
        }
        
        for notification in user_notifications:
            try:
                response = FCMClient.send(
                    notification['user_id'],
                    notification['notification_id'], 
                    notification['title'],
                    notification['body'],
                    notification['data']
                )
                results['success_count'] += 1
                results['results'].append({
                    'user_id': notification['user_id'],
                    'status': 'success',
                    'message_id': response
                })
            except Exception as e:
                results['failed_count'] += 1
                results['results'].append({
                    'user_id': notification['user_id'],
                    'status': 'failed',
                    'error': str(e)
                })
                logger.error(f"Bulk FCM failed for user {notification['user_id']}: {str(e)}")
        
        return results
