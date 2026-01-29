"""
WhatsApp service for sending messages via MSG91 API
"""
import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# MSG91 WhatsApp API endpoint
MSG91_WHATSAPP_API_URL = 'https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/'


def format_phone_number(phone: str) -> str:
    """
    Format phone number with country code.
    - If phone already starts with valid prefix (977, 91, +91, +977, 00977, 0091), use as-is
    - Otherwise, add 91 (India) prefix
    
    Args:
        phone: Phone number string
    
    Returns:
        Formatted phone number with country code
    """
    if not phone:
        return ''
    
    # Strip whitespace
    phone = phone.strip()
    
    # Check if phone already has a valid country code prefix (before removing special chars)
    valid_prefixes = ('+977', '+91', '00977', '0091', '977', '91')
    has_country_code = any(phone.startswith(prefix) for prefix in valid_prefixes)
    
    # Remove spaces, dashes, parentheses, and plus sign - keep only digits
    phone = ''.join(c for c in phone if c.isdigit())
    
    # If no country code was present, add 91 (India)
    if not has_country_code:
        phone = '91' + phone
    
    return phone


def send_order_bill_whatsapp(order, invoice_pdf_url: str) -> bool:
    """
    Send order bill PDF via WhatsApp to customer and vendor using MSG91 API.
    
    Args:
        order: Order model instance
        invoice_pdf_url: Publicly accessible URL to the invoice PDF
    
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    try:
        # Get and format phone numbers
        customer_phone = format_phone_number(order.phone)
        vendor_phone = format_phone_number(order.user.phone) if order.user else ''
        
        # Validate phone numbers
        if not customer_phone and not vendor_phone:
            logger.warning(f'No valid phone numbers for order {order.id}, skipping WhatsApp notification')
            return False
        
        # Build recipient list (only include valid phone numbers)
        recipients = []
        if customer_phone:
            recipients.append(customer_phone)
        if vendor_phone:
            recipients.append(vendor_phone)
        
        # Build payload according to MSG91 API specification
        payload = {
            "integrated_number": getattr(settings, 'MSG91_WHATSAPP_INTEGRATED_NUMBER', ''),
            "content_type": "template",
            "payload": {
                "messaging_product": "whatsapp",
                "type": "template",
                "template": {
                    "name": getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_NAME', ''),
                    "language": {
                        "code": "en",
                        "policy": "deterministic"
                    },
                    "namespace": getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_NAMESPACE', ''),
                    "to_and_components": [
                        {
                            "to": recipients,
                            "components": {
                                "header_1": {
                                    "filename": str(order.id),
                                    "type": "document",
                                    "value": invoice_pdf_url
                                }
                            }
                        }
                    ]
                }
            }
        }
        
        # Set headers
        headers = {
            'Content-Type': 'application/json',
            'authkey': getattr(settings, 'MSG91_AUTH_KEY', '')
        }
        
        # Make API request
        response = requests.post(
            MSG91_WHATSAPP_API_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        # Log response
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('status') == 'success':
                logger.info(
                    f'WhatsApp bill sent successfully for order {order.id} to {recipients}. '
                    f'Request ID: {response_data.get("request_id")}'
                )
                return True
            else:
                logger.error(
                    f'MSG91 API returned error for order {order.id}: {response_data}'
                )
                return False
        else:
            logger.error(
                f'MSG91 API request failed for order {order.id}. '
                f'Status: {response.status_code}, Response: {response.text}'
            )
            return False
            
    except requests.exceptions.Timeout:
        logger.error(f'MSG91 API request timed out for order {order.id}')
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f'MSG91 API request failed for order {order.id}: {str(e)}')
        return False
    except Exception as e:
        logger.error(f'Failed to send WhatsApp bill for order {order.id}: {str(e)}')
        return False
