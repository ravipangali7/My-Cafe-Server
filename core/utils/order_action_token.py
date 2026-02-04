"""Short-lived HMAC token for order accept/reject from notification (no session)."""
import hmac
import hashlib
import base64
import time
from django.conf import settings

ORDER_ACTION_TOKEN_EXPIRY_SECONDS = 600  # 10 minutes


def generate_order_action_token(order_id):
    """Generate a short-lived HMAC token for order accept/reject from notification."""
    expiry_ts = int(time.time()) + ORDER_ACTION_TOKEN_EXPIRY_SECONDS
    payload = f"{order_id}:{expiry_ts}"
    secret = settings.SECRET_KEY.encode('utf-8') if isinstance(settings.SECRET_KEY, str) else settings.SECRET_KEY
    sig = hmac.new(secret, payload.encode('utf-8'), hashlib.sha256).hexdigest()
    raw = f"{expiry_ts}:{sig}"
    return base64.urlsafe_b64encode(raw.encode('utf-8')).decode('ascii').rstrip('=')


def verify_order_action_token(order_id, token):
    """Verify token for order_id; returns True if valid and not expired."""
    if not token:
        return False
    try:
        raw = base64.urlsafe_b64decode(token + '==')
        raw_str = raw.decode('utf-8')
        expiry_str, sig = raw_str.split(':', 1)
        expiry_ts = int(expiry_str)
        if expiry_ts < int(time.time()):
            return False
        payload = f"{order_id}:{expiry_ts}"
        secret = settings.SECRET_KEY.encode('utf-8') if isinstance(settings.SECRET_KEY, str) else settings.SECRET_KEY
        expected = hmac.new(secret, payload.encode('utf-8'), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)
    except Exception:
        return False
