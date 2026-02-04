"""
WhatsApp service for sending messages via MSG91 API
"""
import requests
import logging
from django.conf import settings

from core.models import SuperSetting

logger = logging.getLogger(__name__)

# MSG91 WhatsApp API endpoint
MSG91_WHATSAPP_API_URL = 'https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/'


def format_phone_number(phone: str, country_code: str = None) -> str:
    """
    Format phone number with country code.
    - If country_code is provided, use it directly
    - If phone already starts with valid prefix (977, 91, +91, +977, 00977, 0091), use as-is
    - Otherwise, add 91 (India) prefix
    
    Args:
        phone: Phone number string
        country_code: Optional country code to prepend (e.g., '91', '977')
    
    Returns:
        Formatted phone number with country code
    """
    if not phone:
        return ''
    
    # Strip whitespace
    phone = phone.strip()
    
    # If country_code is explicitly provided, use it
    if country_code:
        # Remove any special characters from phone, keep only digits
        phone = ''.join(c for c in phone if c.isdigit())
        # Ensure country_code is clean (digits only)
        country_code = ''.join(c for c in country_code if c.isdigit())
        return country_code + phone
    
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
    # Get and format phone numbers using stored country codes
    customer_country_code = getattr(order, 'country_code', None) or '91'
    customer_phone = format_phone_number(order.phone, customer_country_code)
    
    vendor_country_code = getattr(order.user, 'country_code', None) if order.user else '91'
    vendor_phone = format_phone_number(order.user.phone, vendor_country_code) if order.user else ''
    
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


def send_order_ready_whatsapp(order) -> bool:
    """
    Send "order ready" WhatsApp message to customer using template mycafeready.
    Called when order status changes to 'ready'.

    Args:
        order: Order model instance (with phone, name, table_no, etc.)

    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    try:
        customer_country_code = getattr(order, 'country_code', None) or '91'
        customer_phone = format_phone_number(order.phone, customer_country_code)
        if not customer_phone:
            logger.warning(f'No valid customer phone for order {order.id}, skipping order-ready WhatsApp')
            return False

        template_name = getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_ORDER_READY', 'mycafeready')
        template_namespace = getattr(
            settings, 'MSG91_WHATSAPP_TEMPLATE_CUSTOMER_NAMESPACE',
            getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_VENDOR_NAMESPACE', ''),
        )

        # Typical order-ready template body variables: e.g. {{1}} order id, {{2}} name, {{3}} table
        components = {
            'body_1': {'type': 'text', 'value': str(order.id)},
            'body_2': {'type': 'text', 'value': order.name or 'Customer'},
            'body_3': {'type': 'text', 'value': order.table_no or 'N/A'},
        }

        payload = {
            'integrated_number': getattr(settings, 'MSG91_WHATSAPP_INTEGRATED_NUMBER', ''),
            'content_type': 'template',
            'payload': {
                'messaging_product': 'whatsapp',
                'type': 'template',
                'template': {
                    'name': template_name,
                    'language': {'code': 'en', 'policy': 'deterministic'},
                    'namespace': template_namespace,
                    'to_and_components': [
                        {'to': [customer_phone], 'components': components}
                    ],
                },
            },
        }

        headers = {
            'Content-Type': 'application/json',
            'authkey': getattr(settings, 'MSG91_AUTH_KEY', ''),
        }

        response = requests.post(
            MSG91_WHATSAPP_API_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('status') == 'success':
                logger.info(
                    f'WhatsApp order-ready sent for order {order.id} to {customer_phone}. '
                    f'Template: {template_name}'
                )
                return True
            logger.error(
                f'MSG91 API error for order-ready order {order.id}: {response_data}'
            )
            return False
        logger.error(
            f'MSG91 API failed for order-ready order {order.id}: '
            f'status={response.status_code}, body={response.text}'
        )
        return False
    except requests.exceptions.Timeout:
        logger.error(f'MSG91 API timeout for order-ready order {order.id}')
        return False
    except Exception as e:
        logger.error(f'Failed to send order-ready WhatsApp for order {order.id}: {e}')
        return False


def _get_marketing_template_names():
    """Get marketing template names from SuperSetting or Django settings fallback."""
    try:
        super_setting = SuperSetting.objects.filter(id=1).first()
        if super_setting:
            template_marketing = getattr(
                super_setting, 'whatsapp_template_marketing', None
            ) or getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_MARKETING', 'mycafemarketing')
            template_imagemarketing = getattr(
                super_setting, 'whatsapp_template_imagemarketing', None
            ) or getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_IMAGE_MARKETING', 'mycafeimagemarketing')
            return template_marketing, template_imagemarketing
    except Exception:
        pass
    return (
        getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_MARKETING', 'mycafemarketing'),
        getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_IMAGE_MARKETING', 'mycafeimagemarketing'),
    )


def _send_marketing_whatsapp_single(
    phone: str,
    message: str,
    image_url: str,
    template_name: str,
    template_namespace: str,
    has_image: bool,
    notification_id: int,
) -> bool:
    """
    Send a single marketing WhatsApp message (text or text+image template).
    """
    try:
        components = {}
        if has_image and image_url:
            components['header_1'] = {
                'type': 'image',
                'value': image_url,
            }
        # Body component: dynamic text (message)
        components['body_1'] = {
            'type': 'text',
            'value': message or '',
        }

        payload = {
            'integrated_number': getattr(settings, 'MSG91_WHATSAPP_INTEGRATED_NUMBER', ''),
            'content_type': 'template',
            'payload': {
                'messaging_product': 'whatsapp',
                'type': 'template',
                'template': {
                    'name': template_name,
                    'language': {'code': 'en', 'policy': 'deterministic'},
                    'namespace': template_namespace,
                    'to_and_components': [
                        {'to': [phone], 'components': components}
                    ],
                },
            },
        }

        headers = {
            'Content-Type': 'application/json',
            'authkey': getattr(settings, 'MSG91_AUTH_KEY', ''),
        }

        response = requests.post(
            MSG91_WHATSAPP_API_URL,
            json=payload,
            headers=headers,
            timeout=30,
        )

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('status') == 'success':
                logger.info(
                    f'WhatsApp marketing sent to {phone} for notification #{notification_id}. '
                    f'Template: {template_name}'
                )
                return True
            logger.error(
                f'MSG91 API error for notification #{notification_id} ({phone}): {response_data}'
            )
            return False
        logger.error(
            f'MSG91 API failed for notification #{notification_id} ({phone}): '
            f'status={response.status_code}, body={response.text}'
        )
        return False
    except requests.exceptions.Timeout:
        logger.error(f'MSG91 API timeout for notification #{notification_id} ({phone})')
        return False
    except Exception as e:
        logger.error(f'Failed to send marketing WhatsApp to {phone}: {e}')
        return False


def send_marketing_whatsapp(notification):
    """
    Send marketing WhatsApp to all customers on the notification.
    Updates notification.sent_count after each send; sets status to 'sent' or 'failed'.
    On full success, charges vendor via process_whatsapp_usage(sent_count * whatsapp_per_usage).
    """
    from django.db import transaction as db_transaction
    from core.models import WhatsAppNotification
    from core.utils.transaction_helpers import process_whatsapp_usage

    template_marketing, template_imagemarketing = _get_marketing_template_names()
    namespace = getattr(
        settings, 'MSG91_WHATSAPP_TEMPLATE_CUSTOMER_NAMESPACE',
        getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_VENDOR_NAMESPACE', ''),
    )
    has_image = bool(notification.image)
    template_name = template_imagemarketing if has_image else template_marketing
    image_url = None
    if has_image and notification.image:
        try:
            image_url = notification.image.url
            if not image_url.startswith('http'):
                base = getattr(settings, 'BASE_URL', '').rstrip('/')
                if base:
                    image_url = base + ('/' + image_url.lstrip('/'))
        except Exception as e:
            logger.warning(f'Could not build image URL for notification #{notification.id}: {e}')

    vendor_country_code = getattr(notification.user, 'country_code', None) or '91'
    customers = list(notification.customers.all())
    total = len(customers)
    sent = 0

    for customer in customers:
        phone = format_phone_number(customer.phone, vendor_country_code)
        if not phone:
            continue
        ok = _send_marketing_whatsapp_single(
            phone=phone,
            message=notification.message,
            image_url=image_url or '',
            template_name=template_name,
            template_namespace=namespace,
            has_image=has_image,
            notification_id=notification.id,
        )
        if ok:
            sent += 1
        # Update progress in DB
        WhatsAppNotification.objects.filter(pk=notification.pk).update(
            sent_count=sent,
        )

    # Reload notification to get latest sent_count
    notification.refresh_from_db()
    all_success = sent == total and total > 0

    with db_transaction.atomic():
        n = WhatsAppNotification.objects.select_for_update().get(pk=notification.pk)
        n.sent_count = sent
        n.status = WhatsAppNotification.STATUS_SENT if all_success else WhatsAppNotification.STATUS_FAILED
        n.save(update_fields=['sent_count', 'status', 'updated_at'])

    # Charge for successfully sent messages (even if some failed), so transactions and due balance reflect actual usage
    if sent > 0:
        try:
            super_setting = SuperSetting.objects.filter(id=1).first()
            if super_setting and getattr(super_setting, 'is_whatsapp_usage', True):
                per_usage = getattr(super_setting, 'whatsapp_per_usage', 0) or 0
                if per_usage > 0:
                    cost = sent * per_usage
                    process_whatsapp_usage(notification.user, cost)
        except Exception as e:
            logger.error(f'Failed to process WhatsApp usage for notification #{notification.id}: {e}')
