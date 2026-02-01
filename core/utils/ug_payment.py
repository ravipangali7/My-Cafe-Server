"""
UG Payment Gateway Client

This module provides a client class for integrating with the UG Payment Gateway (api.ekqr.in).
It handles creating payment orders and checking payment status.
"""

import requests
import logging
import time
from datetime import date
from django.conf import settings

logger = logging.getLogger(__name__)


class UGPaymentClient:
    """
    Client for UG Payment Gateway API.
    
    Usage:
        client = UGPaymentClient()
        result = client.create_order(
            amount=100,
            customer_name="John Doe",
            customer_mobile="9876543210",
            customer_email="john@example.com",
            redirect_url="https://yoursite.com/payment/callback",
            p_info="Order #123",
            udf1="order_123",
            udf2="order",
            udf3="vendor_456"
        )
    """
    
    def __init__(self):
        """Initialize the client with API credentials from settings."""
        self.api_key = getattr(settings, 'UG_API_KEY', '')
        self.base_url = getattr(settings, 'UG_API_BASE_URL', 'https://api.ekqr.in/api')
        self.redirect_base_url = getattr(settings, 'PAYMENT_REDIRECT_BASE_URL', '')
        
        if not self.api_key:
            logger.warning("UG_API_KEY not configured in settings")
    
    def generate_client_txn_id(self, prefix: str, reference_id: int) -> str:
        """
        Generate a unique client transaction ID.
        
        Args:
            prefix: Prefix for the transaction ID (e.g., 'ORD', 'DUE', 'SUB', 'QRS')
            reference_id: Reference ID (order ID, etc.)
        
        Returns:
            Unique transaction ID in format: MYC-{prefix}-{reference_id}-{timestamp}
        """
        timestamp = int(time.time())
        return f"MYC-{prefix}-{reference_id}-{timestamp}"
    
    def create_order(
        self,
        amount: str,
        customer_name: str,
        customer_mobile: str,
        customer_email: str,
        redirect_url: str,
        p_info: str,
        client_txn_id: str,
        udf1: str = "",
        udf2: str = "",
        udf3: str = ""
    ) -> dict:
        """
        Create a payment order with UG Gateway.
        
        Args:
            amount: Payment amount as string (e.g., "100")
            customer_name: Customer's name
            customer_mobile: Customer's mobile number (10 digits)
            customer_email: Customer's email address
            redirect_url: URL to redirect after payment
            p_info: Product/payment information
            client_txn_id: Your unique transaction ID
            udf1: User defined field 1 (e.g., reference ID)
            udf2: User defined field 2 (e.g., payment type)
            udf3: User defined field 3 (e.g., vendor ID)
        
        Returns:
            dict with keys:
                - success: bool
                - order_id: int (UG order ID)
                - payment_url: str (URL to redirect user)
                - message: str (error message if failed)
        """
        url = f"{self.base_url}/create_order"
        
        payload = {
            "key": self.api_key,
            "client_txn_id": client_txn_id,
            "amount": str(amount),
            "p_info": p_info,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_mobile": customer_mobile,
            "redirect_url": redirect_url,
            "udf1": udf1,
            "udf2": udf2,
            "udf3": udf3
        }
        
        try:
            logger.info(f"Creating UG payment order: {client_txn_id}, amount: {amount}")
            
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            data = response.json()
            
            if data.get("status") is True:
                logger.info(f"UG order created successfully: {data.get('data', {}).get('order_id')}")
                return {
                    "success": True,
                    "order_id": data.get("data", {}).get("order_id"),
                    "payment_url": data.get("data", {}).get("payment_url"),
                    "message": data.get("msg", "Order Created")
                }
            else:
                logger.error(f"UG order creation failed: {data.get('msg')}")
                return {
                    "success": False,
                    "order_id": None,
                    "payment_url": None,
                    "message": data.get("msg", "Failed to create order")
                }
                
        except requests.exceptions.Timeout:
            logger.error("UG API request timed out")
            return {
                "success": False,
                "order_id": None,
                "payment_url": None,
                "message": "Payment gateway timeout. Please try again."
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"UG API request failed: {str(e)}")
            return {
                "success": False,
                "order_id": None,
                "payment_url": None,
                "message": f"Payment gateway error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error in create_order: {str(e)}")
            return {
                "success": False,
                "order_id": None,
                "payment_url": None,
                "message": f"Unexpected error: {str(e)}"
            }
    
    def check_order_status(self, client_txn_id: str, txn_date: date) -> dict:
        """
        Check the status of a payment order.
        
        Args:
            client_txn_id: Your unique transaction ID
            txn_date: Date of the transaction
        
        Returns:
            dict with keys:
                - success: bool
                - status: str (success/failure/pending/scanning)
                - utr: str (UPI transaction reference)
                - vpa: str (Customer's VPA)
                - amount: float
                - customer_name: str
                - remark: str
                - message: str (error message if API call failed)
        """
        url = f"{self.base_url}/check_order_status"
        
        # Format date as DD-MM-YYYY
        txn_date_str = txn_date.strftime("%d-%m-%Y")
        
        payload = {
            "key": self.api_key,
            "client_txn_id": client_txn_id,
            "txn_date": txn_date_str
        }
        
        try:
            logger.info(f"Checking UG order status: {client_txn_id}")
            
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            data = response.json()
            
            if data.get("status") is True:
                txn_data = data.get("data", {})
                txn_status = txn_data.get("status", "pending")
                
                logger.info(f"UG order status: {client_txn_id} = {txn_status}")
                
                return {
                    "success": True,
                    "status": txn_status,
                    "utr": txn_data.get("upi_txn_id", ""),
                    "vpa": txn_data.get("customer_vpa", ""),
                    "amount": txn_data.get("amount", 0),
                    "customer_name": txn_data.get("customer_name", ""),
                    "remark": txn_data.get("remark", ""),
                    "udf1": txn_data.get("udf1", ""),
                    "udf2": txn_data.get("udf2", ""),
                    "udf3": txn_data.get("udf3", ""),
                    "message": data.get("msg", "Transaction found")
                }
            else:
                logger.warning(f"UG order not found or error: {data.get('msg')}")
                return {
                    "success": False,
                    "status": "unknown",
                    "utr": "",
                    "vpa": "",
                    "amount": 0,
                    "customer_name": "",
                    "remark": "",
                    "message": data.get("msg", "Transaction not found")
                }
                
        except requests.exceptions.Timeout:
            logger.error("UG status check timed out")
            return {
                "success": False,
                "status": "unknown",
                "utr": "",
                "vpa": "",
                "amount": 0,
                "customer_name": "",
                "remark": "",
                "message": "Payment gateway timeout"
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"UG status check failed: {str(e)}")
            return {
                "success": False,
                "status": "unknown",
                "utr": "",
                "vpa": "",
                "amount": 0,
                "customer_name": "",
                "remark": "",
                "message": f"Payment gateway error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error in check_order_status: {str(e)}")
            return {
                "success": False,
                "status": "unknown",
                "utr": "",
                "vpa": "",
                "amount": 0,
                "customer_name": "",
                "remark": "",
                "message": f"Unexpected error: {str(e)}"
            }
    
    def get_redirect_url(self, client_txn_id: str) -> str:
        """
        Generate the redirect URL for payment callback.
        
        Args:
            client_txn_id: Your unique transaction ID
        
        Returns:
            Full callback URL
        """
        return f"{self.redirect_base_url}/api/payment/callback?txn_id={client_txn_id}"
