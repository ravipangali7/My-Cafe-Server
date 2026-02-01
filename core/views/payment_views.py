"""
Payment views for UG Payment Gateway integration.

This module provides endpoints for initiating, verifying, and handling
payment callbacks from the UG Payment Gateway.
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import redirect
from django.conf import settings as django_settings
from datetime import date
from decimal import Decimal
import json
import logging

from ..models import Transaction, Order, QRStandOrder, User, SuperSetting
from ..utils.ug_payment import UGPaymentClient
from ..utils.transaction_helpers import (
    process_order_transactions,
    process_due_payment,
    process_subscription_payment,
    process_qr_stand_payment
)

logger = logging.getLogger(__name__)


# Payment type constants
PAYMENT_TYPE_ORDER = 'order'
PAYMENT_TYPE_DUES = 'dues'
PAYMENT_TYPE_SUBSCRIPTION = 'subscription'
PAYMENT_TYPE_QR_STAND = 'qr_stand'

# Prefix mapping for client_txn_id generation
PREFIX_MAP = {
    PAYMENT_TYPE_ORDER: 'ORD',
    PAYMENT_TYPE_DUES: 'DUE',
    PAYMENT_TYPE_SUBSCRIPTION: 'SUB',
    PAYMENT_TYPE_QR_STAND: 'QRS'
}


@api_view(['POST'])
def initiate_payment(request):
    """
    Initiate a UG payment for various payment types.
    
    Request body:
        - payment_type: str (order/dues/subscription/qr_stand)
        - reference_id: int (order_id, vendor_id, user_id, qr_stand_order_id)
        - amount: str (payment amount)
        - customer_name: str
        - customer_email: str
        - customer_mobile: str
    
    Returns:
        - payment_url: str (URL to redirect user)
        - ug_client_txn_id: str (transaction ID for verification)
    """
    try:
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        payment_type = data.get('payment_type')
        reference_id = data.get('reference_id')
        amount = data.get('amount')
        customer_name = data.get('customer_name', '')
        customer_email = data.get('customer_email', '')
        customer_mobile = data.get('customer_mobile', '')
        
        # Validate required fields
        if not payment_type:
            return Response(
                {'error': 'payment_type is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if payment_type not in PREFIX_MAP:
            return Response(
                {'error': f'Invalid payment_type. Must be one of: {list(PREFIX_MAP.keys())}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not reference_id:
            return Response(
                {'error': 'reference_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not amount:
            return Response(
                {'error': 'amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not customer_name:
            return Response(
                {'error': 'customer_name is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not customer_mobile:
            return Response(
                {'error': 'customer_mobile is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get reference object and user based on payment type
        user = None
        order = None
        qr_stand_order = None
        p_info = ""
        vendor_id = ""
        
        try:
            reference_id = int(reference_id)
        except ValueError:
            return Response(
                {'error': 'reference_id must be a valid integer'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if payment_type == PAYMENT_TYPE_ORDER:
            try:
                order = Order.objects.get(id=reference_id)
                user = order.user
                p_info = f"Order #{order.id} - My Cafe"
                vendor_id = str(user.id)
            except Order.DoesNotExist:
                return Response(
                    {'error': 'Order not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        elif payment_type == PAYMENT_TYPE_DUES:
            try:
                user = User.objects.get(id=reference_id)
                p_info = f"Due Payment - {user.name}"
                vendor_id = str(user.id)
            except User.DoesNotExist:
                return Response(
                    {'error': 'Vendor not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        elif payment_type == PAYMENT_TYPE_SUBSCRIPTION:
            try:
                user = User.objects.get(id=reference_id)
                p_info = f"Subscription - {user.name}"
                vendor_id = str(user.id)
            except User.DoesNotExist:
                return Response(
                    {'error': 'User not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        elif payment_type == PAYMENT_TYPE_QR_STAND:
            try:
                qr_stand_order = QRStandOrder.objects.get(id=reference_id)
                user = qr_stand_order.vendor
                p_info = f"QR Stand Order #{qr_stand_order.id}"
                vendor_id = str(user.id)
            except QRStandOrder.DoesNotExist:
                return Response(
                    {'error': 'QR Stand Order not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # Initialize UG Payment Client
        ug_client = UGPaymentClient()
        
        # Generate unique client transaction ID
        prefix = PREFIX_MAP[payment_type]
        client_txn_id = ug_client.generate_client_txn_id(prefix, reference_id)
        
        # Generate redirect URL
        redirect_url = ug_client.get_redirect_url(client_txn_id)
        
        # Create UG payment order
        result = ug_client.create_order(
            amount=str(amount),
            customer_name=customer_name,
            customer_mobile=customer_mobile,
            customer_email=customer_email or f"{customer_mobile}@mycafe.com",
            redirect_url=redirect_url,
            p_info=p_info,
            client_txn_id=client_txn_id,
            udf1=str(reference_id),
            udf2=payment_type,
            udf3=vendor_id
        )
        
        if not result['success']:
            return Response(
                {'error': result['message']},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create pending transaction with UG data
        transaction = Transaction.objects.create(
            user=user,
            order=order,
            qr_stand_order=qr_stand_order,
            amount=amount,
            status='pending',
            transaction_type='in',
            transaction_category=payment_type if payment_type != PAYMENT_TYPE_DUES else 'due_paid',
            is_system=False,
            remarks=f"UG Payment initiated for {p_info}",
            ug_order_id=result['order_id'],
            ug_client_txn_id=client_txn_id,
            ug_payment_url=result['payment_url'],
            ug_txn_date=date.today(),
            ug_status='created'
        )
        
        logger.info(f"UG payment initiated: {client_txn_id}, Transaction ID: {transaction.id}")
        
        return Response({
            'success': True,
            'payment_url': result['payment_url'],
            'ug_client_txn_id': client_txn_id,
            'ug_order_id': result['order_id'],
            'transaction_id': transaction.id,
            'message': 'Payment initiated successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error initiating payment: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def verify_payment(request, txn_id):
    """
    Verify the status of a UG payment.
    
    URL params:
        - txn_id: str (ug_client_txn_id)
    
    Returns:
        - status: str (success/failure/pending/scanning)
        - transaction: dict (transaction details)
    """
    try:
        # Find transaction by UG client transaction ID
        try:
            transaction = Transaction.objects.get(ug_client_txn_id=txn_id)
        except Transaction.DoesNotExist:
            return Response(
                {'error': 'Transaction not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # If already processed, return cached status
        if transaction.ug_status in ['success', 'failure']:
            return Response({
                'success': True,
                'status': transaction.ug_status,
                'transaction': {
                    'id': transaction.id,
                    'amount': str(transaction.amount),
                    'utr': transaction.utr,
                    'vpa': transaction.vpa,
                    'status': transaction.status,
                    'ug_status': transaction.ug_status,
                    'ug_remark': transaction.ug_remark,
                    'payment_type': transaction.transaction_category,
                    'created_at': transaction.created_at.isoformat()
                }
            }, status=status.HTTP_200_OK)
        
        # Check status with UG API
        ug_client = UGPaymentClient()
        result = ug_client.check_order_status(txn_id, transaction.ug_txn_date)
        
        if not result['success']:
            return Response({
                'success': False,
                'status': 'unknown',
                'message': result['message'],
                'transaction': {
                    'id': transaction.id,
                    'amount': str(transaction.amount),
                    'status': transaction.status,
                    'ug_status': transaction.ug_status or 'pending'
                }
            }, status=status.HTTP_200_OK)
        
        # Update transaction with UG response
        transaction.ug_status = result['status']
        transaction.ug_remark = result['remark']
        
        if result['utr']:
            transaction.utr = result['utr']
        if result['vpa']:
            transaction.vpa = result['vpa']
        # Save customer_name from UG response to payer_name field
        if result.get('customer_name'):
            transaction.payer_name = result['customer_name']
        
        # Process based on payment status
        if result['status'] == 'success':
            transaction.status = 'success'
            
            # Process the actual payment based on type
            payment_type = result.get('udf2') or transaction.transaction_category
            
            if payment_type == PAYMENT_TYPE_ORDER and transaction.order:
                # Update order payment status
                transaction.order.payment_status = 'paid'
                transaction.order.save()
                
                # Create order transactions only on payment success
                # Get transaction fee from settings
                settings = SuperSetting.objects.first()
                transaction_fee = settings.per_transaction_fee if settings else 10
                
                # Calculate order amount (total - transaction fee)
                order_amount = transaction.amount - Decimal(str(transaction_fee))
                
                # Create transactions with payment data from UG response
                try:
                    process_order_transactions(
                        order=transaction.order,
                        vendor=transaction.user,
                        order_amount=order_amount,
                        transaction_fee=transaction_fee,
                        payment_data={
                            'utr': transaction.utr,
                            'vpa': transaction.vpa,
                            'payer_name': transaction.payer_name
                        }
                    )
                    logger.info(f"Order #{transaction.order.id} transactions created on payment success")
                except Exception as e:
                    logger.error(f"Failed to create order transactions: {str(e)}")
                
                logger.info(f"Order #{transaction.order.id} marked as paid")
            
            elif payment_type == PAYMENT_TYPE_DUES or payment_type == 'due_paid':
                # Process due payment (update due balance)
                from ..utils.transaction_helpers import update_user_due_balance, update_system_balance
                update_user_due_balance(transaction.user, int(transaction.amount), 'subtract')
                update_system_balance(int(transaction.amount), 'add')
                logger.info(f"Due payment processed for user {transaction.user.id}")
            
            elif payment_type == PAYMENT_TYPE_SUBSCRIPTION:
                # Process subscription (extend subscription)
                from dateutil.relativedelta import relativedelta
                from datetime import date as date_type
                
                settings = SuperSetting.objects.first()
                subscription_fee = settings.subscription_fee_per_month if settings else 0
                
                if subscription_fee > 0:
                    months = int(int(transaction.amount) / subscription_fee)
                    user = transaction.user
                    
                    if user.subscription_end_date and user.subscription_end_date > date_type.today():
                        user.subscription_end_date = user.subscription_end_date + relativedelta(months=months)
                    else:
                        user.subscription_start_date = date_type.today()
                        user.subscription_end_date = date_type.today() + relativedelta(months=months)
                    
                    user.save()
                    
                from ..utils.transaction_helpers import update_system_balance
                update_system_balance(int(transaction.amount), 'add')
                logger.info(f"Subscription processed for user {transaction.user.id}")
            
            elif payment_type == PAYMENT_TYPE_QR_STAND and transaction.qr_stand_order:
                # Update QR stand order payment status
                transaction.qr_stand_order.payment_status = 'paid'
                transaction.qr_stand_order.save()
                
                from ..utils.transaction_helpers import update_system_balance
                update_system_balance(int(transaction.amount), 'add')
                logger.info(f"QR Stand Order #{transaction.qr_stand_order.id} marked as paid")
        
        elif result['status'] == 'failure':
            transaction.status = 'failed'
            
            # Update related order status if applicable
            if transaction.order:
                transaction.order.payment_status = 'failed'
                transaction.order.save()
            
            if transaction.qr_stand_order:
                transaction.qr_stand_order.payment_status = 'failed'
                transaction.qr_stand_order.save()
        
        transaction.save()
        
        return Response({
            'success': True,
            'status': result['status'],
            'transaction': {
                'id': transaction.id,
                'amount': str(transaction.amount),
                'utr': transaction.utr,
                'vpa': transaction.vpa,
                'status': transaction.status,
                'ug_status': transaction.ug_status,
                'ug_remark': transaction.ug_remark,
                'payment_type': transaction.transaction_category,
                'created_at': transaction.created_at.isoformat()
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error verifying payment: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def payment_callback(request):
    """
    Handle redirect callback from UG Payment Gateway.
    
    This endpoint receives the redirect from UG after payment completion
    and redirects to the frontend payment status page.
    
    Query params:
        - txn_id: str (ug_client_txn_id, added by our redirect_url)
        - client_txn_id: str (alternative from UG)
    """
    try:
        # Get transaction ID from query params
        txn_id = request.GET.get('txn_id') or request.GET.get('client_txn_id')
        
        if not txn_id:
            # Redirect to frontend with error
            base_url = getattr(django_settings, 'PAYMENT_REDIRECT_BASE_URL', '')
            return redirect(f"{base_url}/payment/status?error=missing_txn_id")
        
        # Find transaction
        try:
            transaction = Transaction.objects.get(ug_client_txn_id=txn_id)
        except Transaction.DoesNotExist:
            base_url = getattr(django_settings, 'PAYMENT_REDIRECT_BASE_URL', '')
            return redirect(f"{base_url}/payment/status?error=transaction_not_found")
        
        # Check status with UG API
        ug_client = UGPaymentClient()
        result = ug_client.check_order_status(txn_id, transaction.ug_txn_date)
        
        # Update transaction status
        if result['success']:
            transaction.ug_status = result['status']
            transaction.ug_remark = result['remark']
            
            if result['utr']:
                transaction.utr = result['utr']
            if result['vpa']:
                transaction.vpa = result['vpa']
            # Save customer_name from UG response to payer_name field
            if result.get('customer_name'):
                transaction.payer_name = result['customer_name']
            
            if result['status'] == 'success':
                transaction.status = 'success'
                
                # Get payment type for proper handling
                payment_type = result.get('udf2') or transaction.transaction_category
                
                # Update related entities and create transactions
                if transaction.order and payment_type == PAYMENT_TYPE_ORDER:
                    transaction.order.payment_status = 'paid'
                    transaction.order.save()
                    
                    # Create order transactions only on payment success
                    settings = SuperSetting.objects.first()
                    transaction_fee = settings.per_transaction_fee if settings else 10
                    order_amount = transaction.amount - Decimal(str(transaction_fee))
                    
                    try:
                        process_order_transactions(
                            order=transaction.order,
                            vendor=transaction.user,
                            order_amount=order_amount,
                            transaction_fee=transaction_fee,
                            payment_data={
                                'utr': transaction.utr,
                                'vpa': transaction.vpa,
                                'payer_name': transaction.payer_name
                            }
                        )
                        logger.info(f"Order #{transaction.order.id} transactions created on payment success")
                    except Exception as e:
                        logger.error(f"Failed to create order transactions: {str(e)}")
                
                if transaction.qr_stand_order and payment_type == PAYMENT_TYPE_QR_STAND:
                    transaction.qr_stand_order.payment_status = 'paid'
                    transaction.qr_stand_order.save()
                    
                    from ..utils.transaction_helpers import update_system_balance
                    update_system_balance(int(transaction.amount), 'add')
                
                # Handle dues and subscription
                if payment_type == PAYMENT_TYPE_DUES or payment_type == 'due_paid':
                    from ..utils.transaction_helpers import update_user_due_balance, update_system_balance
                    update_user_due_balance(transaction.user, int(transaction.amount), 'subtract')
                    update_system_balance(int(transaction.amount), 'add')
                
                elif payment_type == PAYMENT_TYPE_SUBSCRIPTION:
                    from dateutil.relativedelta import relativedelta
                    from datetime import date as date_type
                    
                    settings = SuperSetting.objects.first()
                    subscription_fee = settings.subscription_fee_per_month if settings else 0
                    
                    if subscription_fee > 0:
                        months = int(int(transaction.amount) / subscription_fee)
                        user = transaction.user
                        
                        if user.subscription_end_date and user.subscription_end_date > date_type.today():
                            user.subscription_end_date = user.subscription_end_date + relativedelta(months=months)
                        else:
                            user.subscription_start_date = date_type.today()
                            user.subscription_end_date = date_type.today() + relativedelta(months=months)
                        
                        user.save()
                    
                    from ..utils.transaction_helpers import update_system_balance
                    update_system_balance(int(transaction.amount), 'add')
            
            elif result['status'] == 'failure':
                transaction.status = 'failed'
                
                if transaction.order:
                    transaction.order.payment_status = 'failed'
                    transaction.order.save()
                
                if transaction.qr_stand_order:
                    transaction.qr_stand_order.payment_status = 'failed'
                    transaction.qr_stand_order.save()
            
            transaction.save()
        
        # Redirect to frontend payment status page
        base_url = getattr(django_settings, 'PAYMENT_REDIRECT_BASE_URL', '')
        payment_status = transaction.ug_status or 'pending'
        
        return redirect(f"{base_url}/payment/status/{txn_id}?status={payment_status}")
        
    except Exception as e:
        logger.error(f"Error in payment callback: {str(e)}")
        base_url = getattr(django_settings, 'PAYMENT_REDIRECT_BASE_URL', '')
        return redirect(f"{base_url}/payment/status?error=server_error")


@api_view(['GET'])
def payment_status_by_order(request, order_id):
    """
    Get payment status for a specific order.
    
    URL params:
        - order_id: int
    
    Returns:
        - has_payment: bool
        - payment: dict (payment details if exists)
    """
    try:
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response(
                {'error': 'Order not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Find UG payment transaction for this order
        transaction = Transaction.objects.filter(
            order=order,
            ug_client_txn_id__isnull=False
        ).order_by('-created_at').first()
        
        if not transaction:
            return Response({
                'has_payment': False,
                'payment': None
            }, status=status.HTTP_200_OK)
        
        return Response({
            'has_payment': True,
            'payment': {
                'id': transaction.id,
                'ug_client_txn_id': transaction.ug_client_txn_id,
                'ug_order_id': transaction.ug_order_id,
                'ug_payment_url': transaction.ug_payment_url,
                'ug_status': transaction.ug_status,
                'ug_remark': transaction.ug_remark,
                'amount': str(transaction.amount),
                'utr': transaction.utr,
                'vpa': transaction.vpa,
                'status': transaction.status,
                'created_at': transaction.created_at.isoformat()
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting payment status: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def payment_status_by_qr_stand(request, qr_stand_order_id):
    """
    Get payment status for a specific QR stand order.
    
    URL params:
        - qr_stand_order_id: int
    
    Returns:
        - has_payment: bool
        - payment: dict (payment details if exists)
    """
    try:
        try:
            qr_order = QRStandOrder.objects.get(id=qr_stand_order_id)
        except QRStandOrder.DoesNotExist:
            return Response(
                {'error': 'QR Stand Order not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Find UG payment transaction for this QR stand order
        transaction = Transaction.objects.filter(
            qr_stand_order=qr_order,
            ug_client_txn_id__isnull=False
        ).order_by('-created_at').first()
        
        if not transaction:
            return Response({
                'has_payment': False,
                'payment': None
            }, status=status.HTTP_200_OK)
        
        return Response({
            'has_payment': True,
            'payment': {
                'id': transaction.id,
                'ug_client_txn_id': transaction.ug_client_txn_id,
                'ug_order_id': transaction.ug_order_id,
                'ug_payment_url': transaction.ug_payment_url,
                'ug_status': transaction.ug_status,
                'ug_remark': transaction.ug_remark,
                'amount': str(transaction.amount),
                'utr': transaction.utr,
                'vpa': transaction.vpa,
                'status': transaction.status,
                'created_at': transaction.created_at.isoformat()
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error getting payment status: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
