"""
UG Payment API key resolution and client factory.

Centralizes which UG API key is used for:
- Menu-based orders: vendor's User.ug_api (payments routed to vendor account).
- Non-menu payments (dues, subscription, QR stand, post-order): Super Settings ug_api.
Verify/callback use the same key that was used at initiation (inferred from transaction).
"""

from ..models import SuperSetting
from ..utils.ug_payment import UGPaymentClient


def get_ug_api_for_menu_order(vendor_user):
    """
    Return the UG API key for a menu-based order (vendor-specific).
    Menu-based orders use the vendor's UG API so payments are routed to the correct vendor account.
    Raises ValueError with a clear message if the vendor has no ug_api configured.
    """
    key = (vendor_user.ug_api or '').strip()
    if not key:
        raise ValueError(
            "Vendor UG API is not configured. Please set UG API for this vendor to accept menu order payments."
        )
    return key


def get_ug_api_for_non_menu():
    """
    Return the UG API key for non-menu payments (Super Settings).
    Dues, subscription, QR stand, and post-order payments use Super Settings UG API.
    Raises ValueError with a clear message if Super Settings ug_api is not set.
    """
    setting = SuperSetting.objects.first()
    if not setting:
        raise ValueError(
            "Super Settings UG API is not configured. Non-menu payments are disabled."
        )
    key = (setting.ug_api or '').strip()
    if not key:
        raise ValueError(
            "Super Settings UG API is not configured. Non-menu payments are disabled."
        )
    return key


def resolve_ug_api_for_transaction(transaction):
    """
    Resolve the UG API key that was used when this transaction was created.
    Used by verify_payment and payment_callback so status checks use the same key as create_order.
    - If transaction has order_payload (menu-based flow): use transaction.user.ug_api.
    - Otherwise (non-menu): use Super Settings ug_api.
    Raises ValueError if the resolved key is missing.
    """
    if transaction.order_payload:
        # Menu-based order: payment was initiated with vendor's UG API.
        if not transaction.user_id:
            raise ValueError("UG API not configured for this payment (no vendor on transaction).")
        key = (transaction.user.ug_api or '').strip()
        if not key:
            raise ValueError("Vendor UG API not configured for this payment.")
        return key
    # Non-menu payment: was initiated with Super Settings UG API.
    return get_ug_api_for_non_menu()


def get_ug_client(api_key):
    """
    Return a UGPaymentClient configured with the given API key.
    Use this after resolving the key via get_ug_api_for_menu_order, get_ug_api_for_non_menu,
    or resolve_ug_api_for_transaction.
    """
    return UGPaymentClient(api_key=api_key)
