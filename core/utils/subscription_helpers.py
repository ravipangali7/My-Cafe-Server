"""
Helpers for vendor subscription status using effective end date.
Effective end date = expire_date if set, else subscription_end_date.
"""
from datetime import date


def get_effective_subscription_end_date(user):
    """
    Return the effective subscription end date for a vendor.
    Prefer expire_date (set when creating/editing vendor), fallback to subscription_end_date.
    """
    if user.expire_date is not None:
        return user.expire_date
    return user.subscription_end_date


def get_subscription_state(user, today=None):
    """
    Return subscription state based on effective end date.
    Returns one of: 'active', 'expired', 'no_subscription', 'inactive_with_date'.
    """
    if today is None:
        today = date.today()
    effective_end = get_effective_subscription_end_date(user)
    if effective_end is None:
        return 'no_subscription'
    if effective_end < today:
        return 'expired'
    if not user.is_active:
        return 'inactive_with_date'
    return 'active'
