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


def _send_whatsapp_message(phone: str, order_id: int, invoice_pdf_url: str,
                           template_name: str, template_namespace: str,
                           recipient_type: str = 'recipient') -> bool:
    """
    Helper function to send a single WhatsApp message with specified template.
    
    Args:
        phone: Formatted phone number with country code
        order_id: Order ID for logging and filename
        invoice_pdf_url: Publicly accessible URL to the invoice PDF
        template_name: MSG91 WhatsApp template name
        template_namespace: MSG91 WhatsApp template namespace
        recipient_type: Type of recipient for logging ('customer' or 'vendor')
    
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    try:
        # Build payload according to MSG91 API specification
        payload = {
            "integrated_number": getattr(settings, 'MSG91_WHATSAPP_INTEGRATED_NUMBER', ''),
            "content_type": "template",
            "payload": {
                "messaging_product": "whatsapp",
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {
                        "code": "en",
                        "policy": "deterministic"
                    },
                    "namespace": template_namespace,
                    "to_and_components": [
                        {
                            "to": [phone],
                            "components": {
                                "header_1": {
                                    "filename": f'ORDER BILL {str(order_id)}',
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
                    f'WhatsApp bill sent successfully for order {order_id} to {recipient_type} ({phone}). '
                    f'Template: {template_name}. Request ID: {response_data.get("request_id")}'
                )
                return True
            else:
                logger.error(
                    f'MSG91 API returned error for order {order_id} ({recipient_type}): {response_data}'
                )
                return False
        else:
            logger.error(
                f'MSG91 API request failed for order {order_id} ({recipient_type}). '
                f'Status: {response.status_code}, Response: {response.text}'
            )
            return False
            
    except requests.exceptions.Timeout:
        logger.error(f'MSG91 API request timed out for order {order_id} ({recipient_type})')
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f'MSG91 API request failed for order {order_id} ({recipient_type}): {str(e)}')
        return False
    except Exception as e:
        logger.error(f'Failed to send WhatsApp bill for order {order_id} ({recipient_type}): {str(e)}')
        return False


def send_order_bill_whatsapp(order, invoice_pdf_url: str) -> bool:
    """
    Send order bill PDF via WhatsApp to customer and vendor using MSG91 API.
    Uses different templates for customer and vendor.
    
    Args:
        order: Order model instance
        invoice_pdf_url: Publicly accessible URL to the invoice PDF
    
    Returns:
        bool: True if at least one message was sent successfully, False otherwise
    """
    # Get and format phone numbers
    customer_phone = format_phone_number(order.phone)
    vendor_phone = format_phone_number(order.user.phone) if order.user else ''
    
    # Validate phone numbers
    if not customer_phone and not vendor_phone:
        logger.warning(f'No valid phone numbers for order {order.id}, skipping WhatsApp notification')
        return False
    
    customer_success = False
    vendor_success = False
    
    # Send to customer with customer template
    if customer_phone:
        customer_success = _send_whatsapp_message(
            phone=customer_phone,
            order_id=order.id,
            invoice_pdf_url=invoice_pdf_url,
            template_name=getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_CUSTOMER_NAME', ''),
            template_namespace=getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_CUSTOMER_NAMESPACE', ''),
            recipient_type='customer'
        )
    
    # Send to vendor with vendor template
    if vendor_phone:
        vendor_success = _send_whatsapp_message(
            phone=vendor_phone,
            order_id=order.id,
            invoice_pdf_url=invoice_pdf_url,
            template_name=getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_VENDOR_NAME', ''),
            template_namespace=getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_VENDOR_NAMESPACE', ''),
            recipient_type='vendor'
        )
    
    # Return True if at least one message was sent successfully
    return customer_success or vendor_success
