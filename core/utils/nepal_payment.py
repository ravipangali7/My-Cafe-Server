"""
Nepal Payment (OnePG) Gateway Client.
Uses Basic Auth + HMAC-SHA512 signature per DEVELOPER GUIDELINES Gateway Checkout 2025.
"""
import base64
import hmac
import hashlib
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def get_auth_header():
    """Basic Auth header for OnePG API."""
    username = getattr(settings, 'NEPAL_PAYMENT_MERCHANT_NAME', '')
    password = getattr(settings, 'NEPAL_PAYMENT_API_PASSWORD', '')
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {creds}"}


def generate_signature(payload: dict) -> str:
    """Payload: dict with string values. Keys sorted alphabetically, values concatenated."""
    key = getattr(settings, 'NEPAL_PAYMENT_KEY', '')
    sorted_keys = sorted(payload.keys())
    value = "".join(str(payload[k]) for k in sorted_keys)
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha512).hexdigest().lower()


def get_process_id(merchant_txn_id: str, amount: str) -> dict:
    """
    Get ProcessId from OnePG. amount as string (e.g. "100").
    Returns dict: success, process_id, message
    """
    base = getattr(settings, 'NEPAL_PAYMENT_API_BASE', '').rstrip('/')
    url = f"{base}/GetProcessId"
    merchant_id = getattr(settings, 'NEPAL_PAYMENT_MERCHANT_ID', '')
    merchant_name = getattr(settings, 'NEPAL_PAYMENT_MERCHANT_NAME', '')

    payload = {
        "MerchantId": str(merchant_id),
        "MerchantName": merchant_name,
        "Amount": str(amount),
        "MerchantTxnId": merchant_txn_id,
    }
    payload["Signature"] = generate_signature(payload)

    try:
        r = requests.post(
            url,
            json=payload,
            headers={**get_auth_header(), "Content-Type": "application/json"},
            timeout=30,
        )
        data = r.json()
        if data.get("code") == "0" and data.get("data"):
            return {
                "success": True,
                "process_id": data["data"]["ProcessId"],
                "message": data.get("message", "OK"),
            }
        return {
            "success": False,
            "process_id": None,
            "message": data.get("message", "Error") or str(data.get("errors", "")),
        }
    except Exception as e:
        logger.exception("GetProcessId failed")
        return {"success": False, "process_id": None, "message": str(e)}


def check_transaction_status(merchant_txn_id: str) -> dict:
    """
    Check transaction status. Returns dict with success, status (Success/Fail/Pending), data, message.
    """
    base = getattr(settings, 'NEPAL_PAYMENT_API_BASE', '').rstrip('/')
    url = f"{base}/CheckTransactionStatus"
    merchant_id = getattr(settings, 'NEPAL_PAYMENT_MERCHANT_ID', '')
    merchant_name = getattr(settings, 'NEPAL_PAYMENT_MERCHANT_NAME', '')

    payload = {
        "MerchantId": str(merchant_id),
        "MerchantName": merchant_name,
        "MerchantTxnId": merchant_txn_id,
    }
    payload["Signature"] = generate_signature(payload)

    try:
        r = requests.post(
            url,
            json=payload,
            headers={**get_auth_header(), "Content-Type": "application/json"},
            timeout=30,
        )
        data = r.json()
        if data.get("code") == "0" and data.get("data"):
            return {
                "success": True,
                "status": data["data"].get("Status", "Pending"),
                "data": data["data"],
                "message": data.get("message", "OK"),
            }
        return {
            "success": False,
            "status": None,
            "data": None,
            "message": data.get("message", "Error") or str(data.get("errors", "")),
        }
    except Exception as e:
        logger.exception("CheckTransactionStatus failed")
        return {"success": False, "status": None, "data": None, "message": str(e)}
