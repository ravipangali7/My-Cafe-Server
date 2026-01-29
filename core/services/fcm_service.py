"""
FCM (Firebase Cloud Messaging) service for sending push notifications
"""
import json
import os
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Try to import firebase_admin, but handle gracefully if not installed
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    from firebase_admin.messaging import (
        WebpushConfig,
        WebpushNotification,
        AndroidConfig,
        AndroidNotification,
        APNSConfig,
        APNSPayload,
        Aps,
        ApsAlert,
    )
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


def get_product_image_url(product):
    """
    Get the absolute URL for a product image.
    Returns empty string if no image is available.
    """
    if product and product.image:
        try:
            return f"https://mycafe.sewabyapar.com{product.image.url}"
        except Exception:
            return ""
    return ""


def send_incoming_order_to_vendor(order):
    """
    Send HIGH PRIORITY FCM to all vendor devices for an incoming order.
    Called on order create only. Uses FcmToken table for order.user.
    Data includes: type, order_id, total, items_count, name, table_no, phone, items.
    Items include: name, variant, quantity, price, total, original_price, image_url.
    """
    if not FIREBASE_AVAILABLE:
        logger.warning("Firebase Admin SDK not available. Cannot send incoming order alert.")
        return

    from ..models import FcmToken

    tokens = list(
        FcmToken.objects.filter(user=order.user).values_list("token", flat=True).distinct()
    )
    if not tokens:
        logger.warning(f"No FCM tokens for vendor user id={order.user_id}, skipping incoming order alert.")
        return

    items_qs = order.items.select_related("product", "product_variant__unit")
    items_count = items_qs.count()
    items_list = [
        {
            "n": str(item.product.name if item.product else "Unknown"),  # product name
            "v": str(item.product_variant.unit.symbol if item.product_variant and item.product_variant.unit else ""),  # variant
            "q": str(item.quantity or 1),  # quantity
            "p": str(item.price or 0),  # final price (after discount)
            "t": str(item.total or 0),  # line total
            "op": str(item.product_variant.price if item.product_variant else item.price or 0),  # original price (before discount)
            "img": get_product_image_url(item.product),  # product image URL
        }
        for item in items_qs
    ]
    data_dict = {
        "type": "incoming_order",
        "order_id": str(order.id),
        "total": str(order.total),
        "items_count": str(items_count),
        "name": str(order.name or ""),
        "table_no": str(order.table_no or ""),
        "phone": str(getattr(order, "phone", "") or ""),
        "items": json.dumps(items_list),
    }

    title = "New order"
    body = f"Order #{order.id} - {order.name or 'Customer'} - Table {order.table_no} - ₹{order.total}"

    if not initialize_firebase():
        return

    for token in tokens:
        try:
            # IMPORTANT: Send DATA-ONLY message (no notification field)
            # This ensures onMessageReceived() is called in Android even when app is killed/background
            # Our native MyCafeFirebaseMessagingService handles: notification, ringtone, call UI
            message = messaging.Message(
                data=data_dict,
                token=token,
                # Android: data-only with high priority - no notification field
                # This triggers onMessageReceived() regardless of app state
                android=AndroidConfig(
                    priority="high",
                    # NOTE: Do NOT add notification here - it would bypass our native handler
                ),
                # iOS: Keep APNs config for background wake
                apns=APNSConfig(
                    headers={"apns-priority": "10"},
                    payload=APNSPayload(
                        aps=Aps(
                            content_available=True,
                            # Alert for iOS since it doesn't have our native handler
                            alert=ApsAlert(title=title, body=body),
                            sound="default",
                        )
                    ),
                ),
            )
            messaging.send(message)
            logger.info(f"Sent incoming_order FCM (data-only) for order {order.id} to token ...{token[-8:]}")
        except messaging.UnregisteredError:
            logger.warning(f"FCM token unregistered, skipping: ...{token[-8:]}")
        except Exception as e:
            logger.error(f"Failed to send incoming_order FCM to token ...{token[-8:]}: {e}")


def send_dismiss_incoming_to_vendor(user, order_id, action):
    """
    Send FCM to all vendor devices to dismiss incoming order UI (stop ringtone/vibration).
    action: 'accept' or 'reject'. Called after order status is updated to accepted/rejected.
    """
    if not FIREBASE_AVAILABLE:
        return

    from ..models import FcmToken

    tokens = list(
        FcmToken.objects.filter(user=user).values_list("token", flat=True).distinct()
    )
    if not tokens:
        return

    data_dict = {
        "type": "dismiss_incoming",
        "order_id": str(order_id),
        "action": str(action),
    }

    if not initialize_firebase():
        return

    for token in tokens:
        try:
            message = messaging.Message(
                data=data_dict,
                token=token,
                android=AndroidConfig(priority="high"),
                apns=APNSConfig(headers={"apns-priority": "10"}),
            )
            messaging.send(message)
            logger.info(f"Sent dismiss_incoming FCM order_id={order_id} action={action} to token ...{token[-8:]}")
        except messaging.UnregisteredError:
            logger.warning(f"FCM token unregistered, skipping: ...{token[-8:]}")
        except Exception as e:
            logger.error(f"Failed to send dismiss_incoming FCM: {e}")
