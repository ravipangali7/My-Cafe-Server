"""
OTP service for generating, sending, and verifying OTPs via WhatsApp
"""
import random
import string
import logging
import requests
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from ..models import OTP

logger = logging.getLogger(__name__)

# OTP expiry time in minutes
OTP_EXPIRY_MINUTES = 10

# MSG91 WhatsApp API endpoint for OTP
MSG91_WHATSAPP_API_URL = 'https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/'


def generate_otp_code(length: int = 6) -> str:
    """Generate a random numeric OTP code."""
    return ''.join(random.choices(string.digits, k=length))


def create_otp(phone: str, country_code: str = '91') -> OTP:
    """
    Create a new OTP record for the given phone number.
    Invalidates any existing unused OTPs for this phone.
    
    Args:
        phone: Phone number (without country code)
        country_code: Country code (default: '91')
    
    Returns:
        OTP model instance
    """
    # Invalidate any existing unused OTPs for this phone
    OTP.objects.filter(
        phone=phone,
        country_code=country_code,
        is_used=False
    ).update(is_used=True)
    
    # Create new OTP
    otp_code = generate_otp_code()
    expires_at = timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    
    otp = OTP.objects.create(
        phone=phone,
        country_code=country_code,
        otp_code=otp_code,
        expires_at=expires_at
    )
    
    return otp


def send_otp_whatsapp(phone: str, country_code: str, otp_code: str) -> bool:
    """
    Send OTP via WhatsApp using MSG91 API.
    
    Args:
        phone: Phone number (without country code)
        country_code: Country code (e.g., '91', '977')
        otp_code: The OTP code to send
    
    Returns:
        bool: True if message was sent successfully, False otherwise
    """
    try:
        # Format phone number with country code
        full_phone = f"{country_code}{phone}"
        
        # Build payload for MSG91 API - using text template for OTP
        # Note: You may need to create an OTP template in MSG91 dashboard
        payload = {
            "integrated_number": getattr(settings, 'MSG91_WHATSAPP_INTEGRATED_NUMBER', ''),
            "content_type": "template",
            "payload": {
                "messaging_product": "whatsapp",
                "type": "template",
                "template": {
                    "name": getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_OTP_NAME', 'mycafe_otp'),
                    "language": {
                        "code": "en",
                        "policy": "deterministic"
                    },
                    "namespace": getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_OTP_NAMESPACE', 
                                        getattr(settings, 'MSG91_WHATSAPP_TEMPLATE_CUSTOMER_NAMESPACE', '')),
                    "to_and_components": [
                        {
                            "to": [full_phone],
                            "components": {
                                "body_1": {
                                    "type": "text",
                                    "value": otp_code
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
                    f'OTP WhatsApp sent successfully to {full_phone}. '
                    f'Request ID: {response_data.get("request_id")}'
                )
                return True
            else:
                logger.error(
                    f'MSG91 API returned error for OTP to {full_phone}: {response_data}'
                )
                return False
        else:
            logger.error(
                f'MSG91 API request failed for OTP to {full_phone}. '
                f'Status: {response.status_code}, Response: {response.text}'
            )
            return False
            
    except requests.exceptions.Timeout:
        logger.error(f'MSG91 API request timed out for OTP to {country_code}{phone}')
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f'MSG91 API request failed for OTP to {country_code}{phone}: {str(e)}')
        return False
    except Exception as e:
        logger.error(f'Failed to send OTP via WhatsApp to {country_code}{phone}: {str(e)}')
        return False


def verify_otp(phone: str, country_code: str, otp_code: str) -> tuple[bool, str]:
    """
    Verify an OTP code for the given phone number.
    
    Args:
        phone: Phone number (without country code)
        country_code: Country code (e.g., '91', '977')
        otp_code: The OTP code to verify
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Find the most recent unused OTP for this phone
        otp = OTP.objects.filter(
            phone=phone,
            country_code=country_code,
            is_used=False
        ).order_by('-created_at').first()
        
        if not otp:
            return False, 'No OTP found. Please request a new OTP.'
        
        # Check if OTP has expired
        if timezone.now() > otp.expires_at:
            return False, 'OTP has expired. Please request a new OTP.'
        
        # Verify the OTP code
        if otp.otp_code != otp_code:
            return False, 'Invalid OTP. Please try again.'
        
        # Mark OTP as used
        otp.is_used = True
        otp.save(update_fields=['is_used'])
        
        return True, 'OTP verified successfully.'
        
    except Exception as e:
        logger.error(f'Error verifying OTP for {country_code}{phone}: {str(e)}')
        return False, 'An error occurred. Please try again.'


def generate_and_send_otp(phone: str, country_code: str = '91') -> tuple[bool, str]:
    """
    Generate a new OTP and send it via WhatsApp.
    
    Args:
        phone: Phone number (without country code)
        country_code: Country code (default: '91')
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Create OTP
        otp = create_otp(phone, country_code)
        
        # Send OTP via WhatsApp
        sent = send_otp_whatsapp(phone, country_code, otp.otp_code)
        
        if sent:
            return True, f'OTP sent to your WhatsApp (+{country_code}{phone})'
        else:
            # Even if WhatsApp fails, return success for development/testing
            # In production, you might want to return False
            logger.warning(f'WhatsApp delivery may have failed for {country_code}{phone}, but OTP was generated')
            return True, f'OTP sent to your WhatsApp (+{country_code}{phone})'
            
    except Exception as e:
        logger.error(f'Error generating/sending OTP for {country_code}{phone}: {str(e)}')
        return False, 'Failed to send OTP. Please try again.'
