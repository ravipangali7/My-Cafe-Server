"""
Payment views for UG Payment Gateway integration.

This module provides endpoints for initiating, verifying, and handling
payment callbacks from the UG Payment Gateway.
"""

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import redirect
from django.conf import settings as django_settings
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import logging
import time


def get_ist_date():
    """
    Get current date in IST (Indian Standard Time = UTC+5:30).
    UG payment gateway (ekQR) is based in India and uses IST.
    """
    ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    return ist_now.date()

from ..models import Transaction, Order, OrderItem, QRStandOrder, User, SuperSetting, Product, ProductVariant
from ..utils.ug_payment import UGPaymentClient
from ..services.ug_payment_service import (
    get_ug_api_for_menu_order,
    get_ug_api_for_non_menu,
    resolve_ug_api_for_transaction,
    get_ug_client,
)
from ..utils.transaction_helpers import (
    process_order_transactions,
    process_due_payment,
    process_subscription_payment,
    process_qr_stand_payment
)
from ..services.fcm_service import send_incoming_order_to_vendor
from ..utils.nepal_payment import get_process_id, check_transaction_status
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

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


def _create_order_from_payload(transaction):
    """Create Order from transaction.order_payload (Nepal/UG initiate-order flow). Idempotent if order already set."""
    if transaction.order is not None or not transaction.order_payload:
        return
    # Do not create order if vendor has gone offline since payment was initiated
    order_user = User.objects.get(pk=transaction.user_id)
    if not order_user.is_online:
        logger.warning(f"Skipping order creation for transaction {transaction.id}: vendor {order_user.id} is offline")
        return
    payload = transaction.order_payload
    try:
        order = Order.objects.create(
            name=payload['name'],
            phone=payload['phone'],
            table_no=payload.get('table_no') or '',
            order_type=payload.get('order_type') or 'table',
            address=payload.get('address') or '',
            status='pending',
            payment_status='paid',
            payment_method='online',
            total=transaction.amount,
            fcm_token=payload.get('fcm_token') or '',
            user=order_user
        )
        items_list = json.loads(payload['items']) if isinstance(payload['items'], str) else payload['items']
        for item_data in items_list:
            product_id = item_data.get('product_id')
            product_variant_id = item_data.get('product_variant_id')
            quantity = item_data.get('quantity', 1)
            price = item_data.get('price', '0')
            if product_id and product_variant_id:
                try:
                    product = Product.objects.get(id=product_id, user=order_user)
                    product_variant = ProductVariant.objects.get(id=product_variant_id, product=product)
                    item_total = Decimal(str(price)) * int(quantity)
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        product_variant=product_variant,
                        price=Decimal(str(price)),
                        quantity=int(quantity),
                        total=item_total
                    )
                except (Product.DoesNotExist, ProductVariant.DoesNotExist):
                    pass
        transaction.order = order
        transaction.save(update_fields=['order'])
        super_settings = SuperSetting.objects.first()
        transaction_fee = super_settings.per_transaction_fee if super_settings else 10
        order_amount = transaction.amount - Decimal(str(transaction_fee))
        process_order_transactions(
            order=order,
            vendor=order_user,
            order_amount=order_amount,
            transaction_fee=transaction_fee,
            payment_data={
                'utr': transaction.utr,
                'vpa': transaction.vpa,
                'payer_name': transaction.payer_name
            }
        )
        send_incoming_order_to_vendor(order)
        logger.info(f"Order #{order.id} created on payment success (Nepal/initiate-order flow)")
    except Exception as e:
        logger.error(f"Failed to create order from payload: {str(e)}")


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
        
        # Dues, subscription, QR stand, and post-order payments use Super Settings UG API.
        try:
            ug_api = get_ug_api_for_non_menu()
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        ug_client = get_ug_client(ug_api)
        
        # Generate unique client transaction ID
        prefix = PREFIX_MAP[payment_type]
        client_txn_id = ug_client.generate_client_txn_id(prefix, reference_id)
        
        # Generate redirect URL (UG will append ?client_txn_id=XXX&txn_id=YYY)
        redirect_url = ug_client.get_redirect_url()
        
        # Log the redirect URL being sent to UG for debugging
        logger.info(f"Payment initiation for {client_txn_id}: redirect_url={redirect_url}")
        
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
        # Use IST date since UG (ekQR) is an Indian gateway using IST timezone
        ist_date = get_ist_date()
        logger.info(f"Using IST date for UG transaction: {ist_date}")
        
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
            ug_txn_date=ist_date,
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


@api_view(['POST'])
def initiate_order_payment(request):
    """
    Initiate payment for a menu order without creating the order first.
    Order is created only on payment success (in payment_callback).
    Request body: name, phone, table_no (optional), vendor_phone, total, items (JSON), fcm_token (optional).
    Phone is passed as-is to the payment gateway with no length validation.
    Returns: payment_url, ug_client_txn_id.
    """
    try:
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST

        name = data.get('name')
        phone = data.get('phone')
        table_no = data.get('table_no') or ''
        order_type = data.get('order_type') or 'table'
        address = (data.get('address') or '').strip()
        vendor_phone = data.get('vendor_phone')
        total = data.get('total')
        items_data = data.get('items', '[]')
        fcm_token = data.get('fcm_token') or ''

        if not name or not phone:
            return Response(
                {'error': 'Name and phone are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not vendor_phone:
            return Response(
                {'error': 'vendor_phone is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not total:
            return Response(
                {'error': 'total is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            order_user = User.objects.get(phone=vendor_phone, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if not order_user.is_online:
            return Response(
                {'error': 'Restaurant is currently offline. Orders cannot be placed at this time.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if order_type == 'delivery' and not address:
            return Response(
                {'error': 'Address is required for delivery orders.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        super_settings = SuperSetting.objects.first()
        transaction_fee = super_settings.per_transaction_fee if super_settings else 10
        order_amount = Decimal(str(total))
        total_with_fee = order_amount + Decimal(str(transaction_fee))
        items_str = items_data if isinstance(items_data, str) else json.dumps(items_data)

        # Nepal (977): use OnePG gateway; no 10-digit mobile requirement
        if str(order_user.country_code or '').strip() == '977':
            nep_pass = getattr(django_settings, 'NEPAL_PAYMENT_API_PASSWORD', '') or ''
            nep_key = getattr(django_settings, 'NEPAL_PAYMENT_KEY', '') or ''
            if not nep_pass.strip() or not nep_key.strip():
                return Response(
                    {
                        'error': (
                            'Nepal Payment is not configured. Please set NEPAL_PAYMENT_API_PASSWORD '
                            'and NEPAL_PAYMENT_KEY in the server environment.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            digits = ''.join(c for c in str(phone or '').strip() if c.isdigit())
            phone_normalized = digits if digits else str(phone or '').strip()
            order_payload = {
                'name': name,
                'phone': phone_normalized,
                'table_no': table_no or '',
                'order_type': order_type,
                'address': address,
                'vendor_phone': vendor_phone,
                'total': str(total),
                'items': items_str,
                'fcm_token': fcm_token,
            }
            transaction = Transaction.objects.create(
                user=order_user,
                order=None,
                qr_stand_order=None,
                amount=total_with_fee,
                status='pending',
                transaction_type='in',
                transaction_category=PAYMENT_TYPE_ORDER,
                is_system=False,
                remarks='Nepal Order payment (order will be created on success)',
                order_payload=order_payload,
            )
            merchant_txn_id = f"ORD-{transaction.id}-{int(time.time())}"
            transaction.nepal_merchant_txn_id = merchant_txn_id
            transaction.save(update_fields=['nepal_merchant_txn_id'])

            result = get_process_id(merchant_txn_id, str(total_with_fee))
            if not result.get('success'):
                err_msg = result.get('message') or 'Failed to create payment'
                logger.warning(
                    'Nepal get_process_id failed: vendor_id=%s vendor_phone=%s merchant_txn_id=%s result=%s',
                    order_user.id, order_user.phone, merchant_txn_id, result
                )
                transaction.delete()
                return Response(
                    {'error': err_msg},
                    status=status.HTTP_400_BAD_REQUEST
                )

            gateway_url = getattr(django_settings, 'NEPAL_PAYMENT_GATEWAY_URL', '')
            base_url = getattr(django_settings, 'BASE_URL', '').rstrip('/')
            response_url_backend = f"{base_url}/api/payment/nepal/response/" if base_url else ''
            form_data = {
                'MerchantId': str(getattr(django_settings, 'NEPAL_PAYMENT_MERCHANT_ID', '')),
                'MerchantName': getattr(django_settings, 'NEPAL_PAYMENT_MERCHANT_NAME', ''),
                'Amount': str(total_with_fee),
                'MerchantTxnId': merchant_txn_id,
                'ProcessId': result['process_id'],
                'TransactionRemarks': 'My Cafe Order',
                'ResponseUrl': response_url_backend,
            }
            return Response({
                'success': True,
                'gateway_url': gateway_url,
                'form_data': form_data,
                'merchant_txn_id': merchant_txn_id,
                'transaction_id': transaction.id,
                'message': 'Payment initiated successfully',
            }, status=status.HTTP_200_OK)

        # UG (India etc.): 10-digit mobile and UG gateway
        digits = ''.join(c for c in str(phone or '').strip() if c.isdigit())
        customer_mobile_10 = digits[-10:] if len(digits) >= 10 else digits
        if len(customer_mobile_10) != 10:
            return Response(
                {'error': 'Customer mobile number must be 10 digits'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            ug_api = get_ug_api_for_menu_order(order_user)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        order_payload = {
            'name': name,
            'phone': customer_mobile_10,
            'table_no': table_no or '',
            'order_type': order_type,
            'address': address,
            'vendor_phone': vendor_phone,
            'total': str(total),
            'items': items_str,
            'fcm_token': fcm_token,
        }

        ist_date = get_ist_date()
        transaction = Transaction.objects.create(
            user=order_user,
            order=None,
            qr_stand_order=None,
            amount=total_with_fee,
            status='pending',
            transaction_type='in',
            transaction_category=PAYMENT_TYPE_ORDER,
            is_system=False,
            remarks='UG Order payment (order will be created on success)',
            ug_txn_date=ist_date,
            ug_status='created',
            order_payload=order_payload,
        )

        ug_client = get_ug_client(ug_api)
        client_txn_id = ug_client.generate_client_txn_id('ORD', transaction.id)
        redirect_url = ug_client.get_redirect_url()
        p_info = f"Order payment - My Cafe"

        result = ug_client.create_order(
            amount=str(total_with_fee),
            customer_name=name,
            customer_mobile=customer_mobile_10,
            customer_email=f"{customer_mobile_10}@mycafe.com",
            redirect_url=redirect_url,
            p_info=p_info,
            client_txn_id=client_txn_id,
            udf1=str(transaction.id),
            udf2=PAYMENT_TYPE_ORDER,
            udf3=str(order_user.id),
        )

        if not result['success']:
            transaction.delete()
            return Response(
                {'error': result.get('message', 'Failed to create payment')},
                status=status.HTTP_400_BAD_REQUEST
            )

        transaction.ug_order_id = result.get('order_id')
        transaction.ug_client_txn_id = client_txn_id
        transaction.ug_payment_url = result.get('payment_url')
        transaction.save(update_fields=['ug_order_id', 'ug_client_txn_id', 'ug_payment_url'])

        return Response({
            'success': True,
            'payment_url': result['payment_url'],
            'ug_client_txn_id': client_txn_id,
            'transaction_id': transaction.id,
            'message': 'Payment initiated successfully',
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error initiating order payment: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([])  # Allow unauthenticated access - called from frontend callback
@permission_classes([AllowAny])
def verify_payment(request, client_txn_id):
    """
    Verify the status of a UG payment.
    
    NOTE: This endpoint allows unauthenticated access because it's called
    from the frontend payment callback page which may not have session auth.
    
    URL params:
        - client_txn_id: str (ug_client_client_txn_id)
    
    Returns:
        - status: str (success/failure/pending/scanning)
        - transaction: dict (transaction details)
    """
    try:
        # Resolve transaction by UG client_txn_id or Nepal merchant_txn_id
        transaction = Transaction.objects.filter(ug_client_txn_id=client_txn_id).first()
        is_nepal = False
        if not transaction:
            transaction = Transaction.objects.filter(nepal_merchant_txn_id=client_txn_id).first()
            if transaction:
                is_nepal = True
        if not transaction:
            return Response(
                {'error': 'Transaction not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        vendor_phone = transaction.user.phone if transaction.user else None

        # Nepal (OnePG): verify via CheckTransactionStatus and return same JSON shape
        if is_nepal:
            result = check_transaction_status(client_txn_id)
            status_map = {'Success': 'success', 'Fail': 'failure', 'Pending': 'pending'}
            mapped_status = status_map.get(result.get('status') or '', 'pending')
            if result.get('success') and result.get('data'):
                transaction.ug_status = mapped_status
                transaction.status = mapped_status
                if result['data'].get('GatewayReferenceNo'):
                    transaction.utr = result['data']['GatewayReferenceNo']
                transaction.save(update_fields=['ug_status', 'status', 'utr'])
                if mapped_status == 'success' and transaction.order is None and transaction.order_payload:
                    _create_order_from_payload(transaction)
            return Response({
                'success': True,
                'status': mapped_status,
                'transaction': {
                    'id': transaction.id,
                    'amount': str(transaction.amount),
                    'utr': transaction.utr,
                    'vpa': transaction.vpa,
                    'status': transaction.status,
                    'ug_status': transaction.ug_status,
                    'ug_remark': transaction.ug_remark,
                    'payment_type': transaction.transaction_category,
                    'created_at': transaction.created_at.isoformat(),
                    'vendor_phone': vendor_phone
                },
                'message': result.get('message', 'OK'),
            }, status=status.HTTP_200_OK)

        # UG: resolve API key and check status with UG
        try:
            api_key = resolve_ug_api_for_transaction(transaction)
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

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
                    'created_at': transaction.created_at.isoformat(),
                    'vendor_phone': vendor_phone
                }
            }, status=status.HTTP_200_OK)
        
        # Check status with UG API with retry logic for pending/scanning states (same key as initiation).
        ug_client = get_ug_client(api_key)
        
        max_retries = 3
        retry_delay = 2  # seconds
        result = None
        
        for attempt in range(max_retries):
            result = ug_client.check_order_status(client_txn_id, transaction.ug_txn_date)
            
            logger.info(f"verify_payment attempt {attempt + 1}/{max_retries} for {client_txn_id}: "
                       f"success={result['success']}, status={result.get('status', 'N/A')}")
            
            # If we got a definitive status (success or failure), break out of retry loop
            if result['success'] and result['status'] in ['success', 'failure']:
                break
            
            # If still pending/scanning and not last attempt, wait and retry
            if attempt < max_retries - 1 and result['success'] and result['status'] in ['pending', 'scanning']:
                logger.info(f"Status is '{result['status']}', retrying in {retry_delay}s...")
                time.sleep(retry_delay)
        
        if not result or not result['success']:
            return Response({
                'success': False,
                'status': 'unknown',
                'message': result['message'] if result else 'Failed to check status',
                'transaction': {
                    'id': transaction.id,
                    'amount': str(transaction.amount),
                    'status': transaction.status,
                    'ug_status': transaction.ug_status or 'pending',
                    'vendor_phone': vendor_phone
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
            # Resolve payment_type: prefer UDF2 from UG, fallback to transaction_category
            payment_type = result.get('udf2') or transaction.transaction_category
            
            # Detailed logging for debugging payment type resolution
            logger.info(f"Payment type resolution for {client_txn_id}: "
                       f"udf2='{result.get('udf2')}', "
                       f"transaction_category='{transaction.transaction_category}', "
                       f"resolved_payment_type='{payment_type}'")
            
            if payment_type == PAYMENT_TYPE_ORDER:
                if transaction.order is None and transaction.order_payload:
                    # Create order from payload (initiate-order flow: order only after payment success)
                    # Do not create order if vendor has gone offline since payment was initiated
                    order_user = User.objects.get(pk=transaction.user_id)
                    if not order_user.is_online:
                        logger.warning(f"Skipping order creation for transaction {transaction.id}: vendor {order_user.id} is offline")
                    else:
                        try:
                            payload = transaction.order_payload
                            order = Order.objects.create(
                                name=payload['name'],
                                phone=payload['phone'],
                                table_no=payload.get('table_no') or '',
                                order_type=payload.get('order_type') or 'table',
                                address=payload.get('address') or '',
                                status='pending',
                                payment_status='paid',
                                payment_method='online',
                                total=transaction.amount,
                                fcm_token=payload.get('fcm_token') or '',
                                user=order_user
                            )
                            items_list = json.loads(payload['items']) if isinstance(payload['items'], str) else payload['items']
                            for item_data in items_list:
                                product_id = item_data.get('product_id')
                                product_variant_id = item_data.get('product_variant_id')
                                quantity = item_data.get('quantity', 1)
                                price = item_data.get('price', '0')
                                if product_id and product_variant_id:
                                    try:
                                        product = Product.objects.get(id=product_id, user=order_user)
                                        product_variant = ProductVariant.objects.get(id=product_variant_id, product=product)
                                        item_total = Decimal(str(price)) * int(quantity)
                                        OrderItem.objects.create(
                                            order=order,
                                            product=product,
                                            product_variant=product_variant,
                                            price=Decimal(str(price)),
                                            quantity=int(quantity),
                                            total=item_total
                                        )
                                    except (Product.DoesNotExist, ProductVariant.DoesNotExist):
                                        pass
                            transaction.order = order
                            transaction.save(update_fields=['order'])
                            settings = SuperSetting.objects.first()
                            transaction_fee = settings.per_transaction_fee if settings else 10
                            order_amount = transaction.amount - Decimal(str(transaction_fee))
                            process_order_transactions(
                                order=order,
                                vendor=order_user,
                                order_amount=order_amount,
                                transaction_fee=transaction_fee,
                                payment_data={
                                    'utr': transaction.utr,
                                    'vpa': transaction.vpa,
                                    'payer_name': transaction.payer_name
                                }
                            )
                            send_incoming_order_to_vendor(order)
                            logger.info(f"Order #{order.id} created on payment success (verify_payment)")
                        except Exception as e:
                            logger.error(f"Failed to create order from payload in verify_payment: {str(e)}")
                elif transaction.order:
                    # Legacy: order already existed
                    transaction.order.payment_status = 'paid'
                    transaction.order.save()
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
                logger.info(f"Updating QR Stand Order #{transaction.qr_stand_order.id} payment_status to 'paid'")
                transaction.qr_stand_order.payment_status = 'paid'
                transaction.qr_stand_order.save()
                
                from ..utils.transaction_helpers import update_system_balance
                update_system_balance(int(transaction.amount), 'add')
                logger.info(f"QR Stand Order #{transaction.qr_stand_order.id} marked as paid, system balance updated")
            else:
                # Log when no matching payment type handler was found
                logger.warning(f"No handler matched for payment_type='{payment_type}', "
                             f"has_order={transaction.order is not None}, "
                             f"has_qr_stand_order={transaction.qr_stand_order is not None}")
        
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
                'created_at': transaction.created_at.isoformat(),
                'vendor_phone': vendor_phone
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error verifying payment: {str(e)}")
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([])  # No authentication required - UG gateway calls this
@permission_classes([AllowAny])  # Allow unauthenticated access
def payment_callback(request):
    """
    Handle redirect callback from UG Payment Gateway.
    
    This endpoint receives the redirect from UG after payment completion
    and redirects to the frontend payment status page.
    
    NOTE: This endpoint must be publicly accessible (no auth) because
    UG gateway redirects the browser here without any authentication tokens.
    
    Query params (appended by UG gateway):
        - client_txn_id: str (our transaction ID, sent back by UG)
        - txn_id: str (UG's internal transaction ID)
    """
    try:
        # Get transaction ID from query params
        # UG sends: ?client_txn_id=MYC-XXX-N-TIMESTAMP&txn_id=UG_INTERNAL_ID
        # We need client_txn_id (our ID) to find the transaction
        received_client_txn_id = request.GET.get('client_txn_id')
        received_txn_id = request.GET.get('txn_id')
        
        logger.info(f"Payment callback received: client_txn_id={received_client_txn_id}, txn_id={received_txn_id}")
        
        # Prioritize client_txn_id (our ID) over txn_id (UG's ID)
        txn_id = received_client_txn_id
        
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
        
        # Resolve UG API key used at initiation (menu: vendor.ug_api, non-menu: Super Settings ug_api).
        try:
            api_key = resolve_ug_api_for_transaction(transaction)
        except ValueError:
            base_url = getattr(django_settings, 'PAYMENT_REDIRECT_BASE_URL', '')
            return redirect(f"{base_url}/payment/status?error=ug_api_not_configured")
        
        # Check status with UG API with retry logic (same key as initiation).
        # UG may return 'pending' or 'scanning' immediately after payment due to race condition
        ug_client = get_ug_client(api_key)
        
        max_retries = 3
        retry_delay = 2  # seconds
        result = None
        
        for attempt in range(max_retries):
            result = ug_client.check_order_status(txn_id, transaction.ug_txn_date)
            
            logger.info(f"Payment callback attempt {attempt + 1}/{max_retries} for {txn_id}: "
                       f"success={result['success']}, status={result.get('status', 'N/A')}")
            
            # If we got a definitive status (success or failure), break out of retry loop
            if result['success'] and result['status'] in ['success', 'failure']:
                logger.info(f"Got definitive status '{result['status']}' for {txn_id}")
                break
            
            # If still pending/scanning and not last attempt, wait and retry
            if attempt < max_retries - 1:
                logger.info(f"Status is '{result.get('status', 'unknown')}', retrying in {retry_delay}s...")
                time.sleep(retry_delay)
        
        # Update transaction status
        if result and result['success']:
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
                # Resolve payment_type: prefer UDF2 from UG, fallback to transaction_category
                payment_type = result.get('udf2') or transaction.transaction_category
                
                # Detailed logging for debugging payment type resolution
                logger.info(f"[Callback] Payment type resolution for {txn_id}: "
                           f"udf2='{result.get('udf2')}', "
                           f"transaction_category='{transaction.transaction_category}', "
                           f"resolved_payment_type='{payment_type}', "
                           f"has_order={transaction.order is not None}, "
                           f"has_qr_stand_order={transaction.qr_stand_order is not None}")
                
                # Update related entities and create transactions
                if payment_type == PAYMENT_TYPE_ORDER:
                    if transaction.order is None and transaction.order_payload:
                        # Create order from payload (initiate-order flow: order only after payment success)
                        # Do not create order if vendor has gone offline since payment was initiated
                        order_user = User.objects.get(pk=transaction.user_id)
                        if not order_user.is_online:
                            logger.warning(f"[Callback] Skipping order creation for transaction {transaction.id}: vendor {order_user.id} is offline")
                        else:
                            try:
                                payload = transaction.order_payload
                                order = Order.objects.create(
                                    name=payload['name'],
                                    phone=payload['phone'],
                                    table_no=payload.get('table_no') or '',
                                    order_type=payload.get('order_type') or 'table',
                                    address=payload.get('address') or '',
                                    status='pending',
                                    payment_status='paid',
                                    payment_method='online',
                                    total=transaction.amount,
                                    fcm_token=payload.get('fcm_token') or '',
                                    user=order_user
                                )
                                items_list = json.loads(payload['items']) if isinstance(payload['items'], str) else payload['items']
                                for item_data in items_list:
                                    product_id = item_data.get('product_id')
                                    product_variant_id = item_data.get('product_variant_id')
                                    quantity = item_data.get('quantity', 1)
                                    price = item_data.get('price', '0')
                                    if product_id and product_variant_id:
                                        try:
                                            product = Product.objects.get(id=product_id, user=order_user)
                                            product_variant = ProductVariant.objects.get(id=product_variant_id, product=product)
                                            item_total = Decimal(str(price)) * int(quantity)
                                            OrderItem.objects.create(
                                                order=order,
                                                product=product,
                                                product_variant=product_variant,
                                                price=Decimal(str(price)),
                                                quantity=int(quantity),
                                                total=item_total
                                            )
                                        except (Product.DoesNotExist, ProductVariant.DoesNotExist):
                                            pass
                                transaction.order = order
                                transaction.save(update_fields=['order'])
                                settings = SuperSetting.objects.first()
                                transaction_fee = settings.per_transaction_fee if settings else 10
                                order_amount = transaction.amount - Decimal(str(transaction_fee))
                                process_order_transactions(
                                    order=order,
                                    vendor=order_user,
                                    order_amount=order_amount,
                                    transaction_fee=transaction_fee,
                                    payment_data={
                                        'utr': transaction.utr,
                                        'vpa': transaction.vpa,
                                        'payer_name': transaction.payer_name
                                    }
                                )
                                send_incoming_order_to_vendor(order)
                                logger.info(f"Order #{order.id} created on payment success (initiate-order flow)")
                            except Exception as e:
                                logger.error(f"Failed to create order from payload: {str(e)}")
                    elif transaction.order:
                        # Legacy: order already existed before payment
                        transaction.order.payment_status = 'paid'
                        transaction.order.save()
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
                    logger.info(f"[Callback] Updating QR Stand Order #{transaction.qr_stand_order.id} payment_status to 'paid'")
                    transaction.qr_stand_order.payment_status = 'paid'
                    transaction.qr_stand_order.save()
                    
                    from ..utils.transaction_helpers import update_system_balance
                    update_system_balance(int(transaction.amount), 'add')
                    logger.info(f"[Callback] QR Stand Order #{transaction.qr_stand_order.id} marked as paid, system balance updated")
                elif payment_type == PAYMENT_TYPE_QR_STAND and not transaction.qr_stand_order:
                    logger.error(f"[Callback] payment_type is 'qr_stand' but transaction.qr_stand_order is None for {txn_id}")
                
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


@require_GET
@csrf_exempt
def nepal_payment_notification(request):
    """
    OnePG webhook: GET with MerchantTxnId, GatewayTxnId.
    Call CheckTransactionStatus, update transaction, create order on success.
    Return plain text: "received" / "already received".
    """
    merchant_txn_id = request.GET.get('MerchantTxnId')
    request.GET.get('GatewayTxnId')  # optional, for logging
    if not merchant_txn_id:
        return HttpResponse('bad request', status=400)
    try:
        transaction = Transaction.objects.get(nepal_merchant_txn_id=merchant_txn_id)
    except Transaction.DoesNotExist:
        return HttpResponse('transaction not found', status=404)
    if transaction.status == 'success':
        return HttpResponse('already received', content_type='text/plain')
    result = check_transaction_status(merchant_txn_id)
    if not result.get('success'):
        return HttpResponse('check failed', status=500)
    status_map = {'Success': 'success', 'Fail': 'failed', 'Pending': 'pending'}
    tx_status = status_map.get(result.get('status', ''), 'pending')
    transaction.ug_status = tx_status
    transaction.status = tx_status
    if result.get('data') and result['data'].get('GatewayReferenceNo'):
        transaction.utr = result['data']['GatewayReferenceNo']
    transaction.save(update_fields=['ug_status', 'status', 'utr'])
    if tx_status == 'success':
        _create_order_from_payload(transaction)
    return HttpResponse('received', content_type='text/plain')


@require_GET
def nepal_payment_response(request):
    """
    OnePG redirects customer here after payment. Redirect to frontend payment status page with merchant_txn_id.
    """
    merchant_txn_id = request.GET.get('MerchantTxnId')
    base_url = getattr(django_settings, 'PAYMENT_REDIRECT_BASE_URL', '')
    if not merchant_txn_id:
        return redirect(f"{base_url}/payment/status?error=missing_txn_id")
    return redirect(f"{base_url}/payment/status/{merchant_txn_id}")


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
