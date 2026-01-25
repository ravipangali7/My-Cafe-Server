"""
FCM (Firebase Cloud Messaging) service for sending push notifications
"""
import os
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Try to import firebase_admin, but handle gracefully if not installed
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    from firebase_admin.messaging import WebpushConfig, WebpushNotification
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False
    logger.warning("firebase-admin not installed. FCM notifications will be disabled.")


def initialize_firebase():
    """Initialize Firebase Admin SDK if not already initialized"""
    if not FIREBASE_AVAILABLE:
        return False
    
    try:
        # Check if already initialized
        if firebase_admin._apps:
            return True
        
        # Get service account key path from settings
        service_account_path = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_KEY', None)
        
        if not service_account_path:
            logger.warning("FIREBASE_SERVICE_ACCOUNT_KEY not set in settings. FCM notifications disabled.")
            return False
        
        # Check if file exists
        if not os.path.exists(service_account_path):
            logger.warning(f"Firebase service account key not found at {service_account_path}. FCM notifications disabled.")
            return False
        
        # Initialize Firebase Admin SDK
        cred = credentials.Certificate(service_account_path)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {str(e)}")
        return False


def send_fcm_notification(fcm_token: str, title: str, body: str, data: dict = None):
    """
    Send FCM notification to a device token
    
    Args:
        fcm_token: FCM device token
        title: Notification title
        body: Notification body text
        data: Optional dictionary of additional data to send
    
    Returns:
        bool: True if notification sent successfully, False otherwise
    """
    if not FIREBASE_AVAILABLE:
        logger.warning("Firebase Admin SDK not available. Cannot send notification.")
        return False
    
    # Initialize Firebase if not already done
    if not initialize_firebase():
        return False
    
    try:
        # Ensure all data values are strings (required for FCM)
        data_dict = {}
        if data:
            data_dict = {str(k): str(v) for k, v in data.items()}
        
        # Create message with web push configuration for web browsers
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            token=fcm_token,
            data=data_dict,
            webpush=WebpushConfig(
                notification=WebpushNotification(
                    title=title,
                    body=body,
                    icon='/favicon.ico',
                    badge='/favicon.ico',
                ),
                data=data_dict,
            ),
        )
        
        # Send message
        response = messaging.send(message)
        logger.info(f"Successfully sent FCM notification. Message ID: {response}")
        return True
        
    except messaging.UnregisteredError:
        logger.warning(f"FCM token is unregistered: {fcm_token[:20]}...")
        return False
    except messaging.InvalidArgumentError as e:
        logger.error(f"Invalid FCM token or argument: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Failed to send FCM notification: {str(e)}")
        return False
