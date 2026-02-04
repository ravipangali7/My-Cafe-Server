from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import json
import logging
from datetime import datetime
from decimal import Decimal
from django.db.models import Q
from django.core.paginator import Paginator
from ..models import Order, OrderItem, Product, ProductVariant, User, Invoice, SuperSetting, VendorCustomer
from ..serializers import OrderSerializer, OrderItemSerializer
from ..services.fcm_service import send_fcm_notification, send_incoming_order_to_vendor, send_dismiss_incoming_to_vendor
from ..services.pdf_service import generate_order_invoice
from ..services.whatsapp_service import send_order_bill_whatsapp, send_order_ready_whatsapp
from ..utils.order_action_token import verify_order_action_token
# NOTE: process_order_transactions is now called in payment_views.py on payment success

logger = logging.getLogger(__name__)


@api_view(['GET'])
def order_list(request):
    """Get all orders for the authenticated user with filtering, search, and pagination"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Get query parameters
        search = request.GET.get('search', '').strip()
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))
        user_id = request.GET.get('user_id')
        status_filter = request.GET.get('status')
        payment_status = request.GET.get('payment_status')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Filter by user - superusers can see all orders and filter by user_id
        if request.user.is_superuser:
            queryset = Order.objects.all()
            if user_id:
                try:
                    queryset = queryset.filter(user_id=int(user_id))
                except ValueError:
                    pass
        else:
            queryset = Order.objects.filter(user=request.user)
        
        # Apply filters
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Apply search
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(phone__icontains=search) | Q(table_no__icontains=search)
            )
        
        # Prefetch related for performance
        queryset = queryset.prefetch_related('items__product', 'items__product_variant__unit').order_by('-created_at')
        
        # Paginate
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages
        
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1
        
        page_obj = paginator.get_page(page)
        
        serializer = OrderSerializer(page_obj.object_list, many=True, context={'request': request})
        
        return Response({
            'data': serializer.data,
            'count': paginator.count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def order_create(request):
    """Create a new order with items - supports both authenticated and guest orders"""
    try:
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        name = data.get('name')
        phone = data.get('phone')
        table_no = data.get('table_no') or ''
        status_val = data.get('status', 'pending')
        payment_status = data.get('payment_status', 'pending')
        fcm_token = data.get('fcm_token', '')
        items_data = data.get('items', '[]')
        total = data.get('total', '0')
        vendor_phone = data.get('vendor_phone')
        
        if not name or not phone:
            return Response(
                {'error': 'Name and phone are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determine the vendor/user for this order
        # Always use vendor_phone to find the vendor - the user field represents the cafe owner, not the customer
        if not vendor_phone:
            return Response(
                {'error': 'vendor_phone is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            order_user = User.objects.get(phone=vendor_phone, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Fetch transaction fee from settings
        settings = SuperSetting.objects.first()
        transaction_fee = settings.per_transaction_fee if settings else 10
        
        # Calculate order amount (without fee) and total (with fee)
        order_amount = Decimal(str(total))
        total_with_fee = order_amount + Decimal(str(transaction_fee))
        
        # Create order with total including transaction fee (table_no optional)
        order = Order.objects.create(
            name=name,
            phone=phone,
            table_no=table_no or '',
            status=status_val,
            payment_status=payment_status,
            total=total_with_fee,
            fcm_token=fcm_token,
            user=order_user
        )

        # Ensure VendorCustomer exists for this vendor and phone (same vendor: skip; other vendor: new row)
        phone_stripped = (phone or '').strip()
        if phone_stripped:
            VendorCustomer.objects.get_or_create(
                user=order_user,
                phone=phone_stripped,
                defaults={'name': name or 'Customer'}
            )
        
        # Parse and create order items
        try:
            items_list = json.loads(items_data) if isinstance(items_data, str) else items_data
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
                        continue
        except (json.JSONDecodeError, ValueError):
            pass
        
        # NOTE: Transactions are NOT created here anymore.
        # Transactions will be created ONLY after successful UG payment
        # in payment_views.py verify_payment() or payment_callback()
        
        # Send HIGH PRIORITY FCM to all vendor devices (from FcmToken table)
        if status_val == 'pending':
            try:
                send_incoming_order_to_vendor(order)
            except Exception as e:
                logger.error(f'Failed to send incoming order FCM: {str(e)}')

        serializer = OrderSerializer(order, context={'request': request})
        return Response({
            'order': serializer.data,
            'transaction_fee': transaction_fee,
            'order_amount': str(order_amount),
            'total_with_fee': str(total_with_fee)
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def order_detail(request, id):
    """Get a specific order"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can access any order, regular users only their own
        if request.user.is_superuser:
            order = Order.objects.prefetch_related('items__product', 'items__product_variant__unit').get(id=id)
        else:
            order = Order.objects.prefetch_related('items__product', 'items__product_variant__unit').get(id=id, user=request.user)
        serializer = OrderSerializer(order, context={'request': request})
        return Response({'order': serializer.data}, status=status.HTTP_200_OK)
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
def order_edit(request, id):
    """Update an order. Accepts form-data or JSON (e.g. status-only from WebView/native)."""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can edit any order, regular users only their own
        if request.user.is_superuser:
            order = Order.objects.get(id=id)
        else:
            order = Order.objects.get(id=id, user=request.user)
        
        # Support both form-data (POST) and JSON body (e.g. status-only updates)
        if request.content_type and 'application/json' in request.content_type:
            try:
                data = json.loads(request.body)
            except (ValueError, TypeError):
                data = {}
        else:
            data = request.POST
        
        name = data.get('name') or request.POST.get('name')
        phone = data.get('phone') or request.POST.get('phone')
        table_no = data.get('table_no') or request.POST.get('table_no')
        status_val = data.get('status') or request.POST.get('status')
        payment_status = data.get('payment_status') or request.POST.get('payment_status')
        fcm_token = data.get('fcm_token') if 'fcm_token' in data else request.POST.get('fcm_token')
        items_data = data.get('items') or request.POST.get('items')
        total = data.get('total') or request.POST.get('total')
        reject_reason = data.get('reject_reason') if 'reject_reason' in data else request.POST.get('reject_reason')
        
        # Track old status to detect changes
        old_status = order.status
        
        if name:
            order.name = name
        if phone:
            order.phone = phone
        if table_no:
            order.table_no = table_no
        if status_val:
            order.status = status_val
        if payment_status:
            order.payment_status = payment_status
        if fcm_token is not None:
            order.fcm_token = fcm_token
        if total:
            order.total = Decimal(str(total))
        if reject_reason is not None:
            order.reject_reason = reject_reason
        
        order.save()

        # Dismiss incoming order UI on all vendor devices when accept/reject
        if status_val and status_val != old_status and status_val in ('accepted', 'rejected'):
            try:
                send_dismiss_incoming_to_vendor(order.user, order.id, status_val)
            except Exception as e:
                logger.error(f'Failed to send dismiss_incoming FCM for order {order.id}: {str(e)}')

        # Send WhatsApp bill to customer and vendor when order is accepted
        if status_val == 'accepted' and status_val != old_status:
            try:
                # Generate or get invoice
                invoice, _ = Invoice.objects.get_or_create(
                    order=order,
                    defaults={
                        'invoice_number': f'INV-{order.id}-{datetime.now().strftime("%Y%m%d%H%M%S")}',
                        'total_amount': order.total
                    }
                )
                
                # Generate PDF if not exists
                if not invoice.pdf_file or not invoice.pdf_file.name:
                    pdf_file = generate_order_invoice(order)
                    invoice.pdf_file.save(pdf_file.name, pdf_file, save=True)
                
                # Build absolute URL for the PDF
                pdf_url = request.build_absolute_uri(invoice.pdf_file.url)
                
                # Send WhatsApp notification
                send_order_bill_whatsapp(order, pdf_url)
            except Exception as e:
                logger.error(f'Failed to send WhatsApp bill for order {order.id}: {str(e)}')

        # Send WhatsApp "order ready" (mycafeready template) to customer when status changes to ready
        if status_val == 'ready' and status_val != old_status:
            try:
                send_order_ready_whatsapp(order)
            except Exception as e:
                logger.error(f'Failed to send order-ready WhatsApp for order {order.id}: {str(e)}')

        # Send FCM notification to customer if status changed and order.fcm_token exists (customer device)
        if status_val and status_val != old_status and order.fcm_token:
            try:
                status_messages = {
                    'pending': {
                        'title': 'Order Status Update',
                        'body': 'Your Order is Pending right now wait for accept from kitchen'
                    },
                    'accepted': {
                        'title': 'Order Accepted',
                        'body': f'Your Order #{order.id} has been accepted and is being prepared'
                    },
                    'running': {
                        'title': 'Order In Progress',
                        'body': f'Your Order #{order.id} is now being prepared in the kitchen'
                    },
                    'ready': {
                        'title': 'Order Ready',
                        'body': f'Your Order #{order.id} is ready! Please collect from table {order.table_no or "N/A"}'
                    },
                    'rejected': {
                        'title': 'Order Rejected',
                        'body': f'Your Order #{order.id} has been rejected' + (f': {order.reject_reason}' if order.reject_reason else '')
                    },
                    'completed': {
                        'title': 'Order Completed',
                        'body': f'Your Order #{order.id} is ready! Please collect from table {order.table_no or "N/A"}'
                    }
                }
                message = status_messages.get(status_val, {
                    'title': 'Order Status Update',
                    'body': f'Your Order #{order.id} status has been updated to {status_val}'
                })
                send_fcm_notification(
                    fcm_token=order.fcm_token,
                    title=message['title'],
                    body=message['body'],
                    data={
                        'order_id': str(order.id),
                        'status': str(status_val),
                        'table_no': str(order.table_no or '')
                    }
                )
            except Exception as e:
                logger.error(f'Failed to send FCM notification for order {order.id}: {str(e)}')

        # Update items if provided
        if items_data:
            try:
                # Parse incoming items data
                items_list = json.loads(items_data) if isinstance(items_data, str) else items_data
                
                # Handle empty items_data - delete all items (same as current behavior)
                if not items_list:
                    OrderItem.objects.filter(order=order).delete()
                else:
                    # Fetch existing order items from database
                    existing_items = list(OrderItem.objects.filter(order=order))
                    
                    # Build lookup dictionary for existing items keyed by (product_id, product_variant_id)
                    # Handle multiple items with same (product_id, product_variant_id) by matching first, tracking others for deletion
                    existing_dict = {}
                    items_to_delete = []
                    
                    for item in existing_items:
                        key = (item.product_id, item.product_variant_id)
                        if key not in existing_dict:
                            existing_dict[key] = item
                        else:
                            # Duplicate key - mark for deletion
                            items_to_delete.append(item)
                    
                    # Build lookup dictionary for new items from parsed items_data
                    new_items_dict = {}
                    for item_data in items_list:
                        product_id = item_data.get('product_id')
                        product_variant_id = item_data.get('product_variant_id')
                        
                        if product_id and product_variant_id:
                            try:
                                # Convert to integers for comparison
                                product_id = int(product_id)
                                product_variant_id = int(product_variant_id)
                                key = (product_id, product_variant_id)
                                
                                # Store item data with key
                                if key not in new_items_dict:
                                    new_items_dict[key] = item_data
                            except (ValueError, TypeError):
                                # Skip invalid product/variant IDs
                                continue
                    
                    # Process deletions: Find items in DB not present in new list
                    deleted_item_ids = set()
                    for key, existing_item in existing_dict.items():
                        if key not in new_items_dict:
                            items_to_delete.append(existing_item)
                            deleted_item_ids.add(existing_item.id)
                    
                    # Also add duplicate items to deleted set
                    for item in items_to_delete:
                        deleted_item_ids.add(item.id)
                    
                    # Delete items not in new list (including duplicates)
                    if items_to_delete:
                        OrderItem.objects.filter(id__in=[item.id for item in items_to_delete]).delete()
                    
                    # Process updates and creations
                    for key, item_data in new_items_dict.items():
                        product_id, product_variant_id = key
                        quantity = item_data.get('quantity', 1)
                        price = item_data.get('price', '0')
                        
                        try:
                            # Get product and variant (use order.user for consistency)
                            product = Product.objects.get(id=product_id, user=order.user)
                            product_variant = ProductVariant.objects.get(id=product_variant_id, product=product)
                            
                            # Calculate item total
                            item_total = Decimal(str(price)) * int(quantity)
                            new_price = Decimal(str(price))
                            new_quantity = int(quantity)
                            
                            # Check if item exists in DB and wasn't deleted
                            if key in existing_dict and existing_dict[key].id not in deleted_item_ids:
                                # Process updates: Update if quantity/price changed
                                existing_item = existing_dict[key]
                                if (existing_item.quantity != new_quantity or 
                                    existing_item.price != new_price):
                                    existing_item.quantity = new_quantity
                                    existing_item.price = new_price
                                    existing_item.total = item_total
                                    existing_item.save()
                            else:
                                # Process creations: Create items that don't exist in DB or were deleted
                                OrderItem.objects.create(
                                    order=order,
                                    product=product,
                                    product_variant=product_variant,
                                    price=new_price,
                                    quantity=new_quantity,
                                    total=item_total
                                )
                        except (Product.DoesNotExist, ProductVariant.DoesNotExist):
                            # Skip items with invalid product/variant (same as current behavior)
                            continue
            except (json.JSONDecodeError, ValueError):
                # Skip item updates on invalid JSON (same as current behavior)
                pass
        
        serializer = OrderSerializer(order, context={'request': request})
        return Response({'order': serializer.data}, status=status.HTTP_200_OK)
        
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def order_status_from_notification(request, id):
    """
    Update order status from notification action (accept/reject) using a short-lived token.
    No session required. Body: JSON { "status": "accepted"|"rejected", "token": "<action_token>", "reject_reason"?: "..." }.
    """
    try:
        try:
            data = json.loads(request.body) if request.body else {}
        except (ValueError, TypeError):
            data = {}
        status_val = data.get('status', '').strip().lower()
        token = data.get('token', '').strip()
        reject_reason = data.get('reject_reason', '').strip() or None

        if status_val not in ('accepted', 'rejected'):
            return Response(
                {'error': 'status must be "accepted" or "rejected"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not token:
            return Response(
                {'error': 'token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        order_id_str = str(id)
        if not verify_order_action_token(order_id_str, token):
            return Response(
                {'error': 'Invalid or expired token'},
                status=status.HTTP_403_FORBIDDEN
            )

        order = Order.objects.get(id=id)
        old_status = order.status
        order.status = status_val
        if reject_reason is not None:
            order.reject_reason = reject_reason
        order.save()

        if status_val != old_status and status_val in ('accepted', 'rejected'):
            try:
                send_dismiss_incoming_to_vendor(order.user, order.id, status_val)
            except Exception as e:
                logger.error(f'Failed to send dismiss_incoming FCM for order {order.id}: {str(e)}')

        if status_val == 'accepted' and status_val != old_status:
            try:
                invoice, _ = Invoice.objects.get_or_create(
                    order=order,
                    defaults={
                        'invoice_number': f'INV-{order.id}-{datetime.now().strftime("%Y%m%d%H%M%S")}',
                        'total_amount': order.total
                    }
                )
                if not invoice.pdf_file or not invoice.pdf_file.name:
                    pdf_file = generate_order_invoice(order)
                    invoice.pdf_file.save(pdf_file.name, pdf_file, save=True)
                pdf_url = request.build_absolute_uri(invoice.pdf_file.url)
                send_order_bill_whatsapp(order, pdf_url)
            except Exception as e:
                logger.error(f'Failed to send WhatsApp bill for order {order.id}: {str(e)}')

        if status_val and status_val != old_status and order.fcm_token:
            try:
                status_messages = {
                    'accepted': {'title': 'Order Accepted', 'body': f'Your Order #{order.id} has been accepted and is being prepared'},
                    'rejected': {'title': 'Order Rejected', 'body': f'Your Order #{order.id} has been rejected' + (f': {order.reject_reason}' if order.reject_reason else '')}
                }
                msg = status_messages.get(status_val, {'title': 'Order Status Update', 'body': f'Your Order #{order.id} status has been updated to {status_val}'})
                send_fcm_notification(
                    fcm_token=order.fcm_token,
                    title=msg['title'],
                    body=msg['body'],
                    data={'order_id': str(order.id), 'status': str(status_val), 'table_no': str(order.table_no or '')}
                )
            except Exception as e:
                logger.error(f'Failed to send FCM notification for order {order.id}: {str(e)}')

        serializer = OrderSerializer(order, context={'request': request})
        return Response({'order': serializer.data}, status=status.HTTP_200_OK)

    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.exception('order_status_from_notification error')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def order_delete(request, id):
    """Delete an order. Only superusers can delete orders; vendors cannot."""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only superusers can delete orders'},
            status=status.HTTP_403_FORBIDDEN
        )
    try:
        order = Order.objects.get(id=id)
        order.delete()
        return Response({'message': 'Order deleted successfully'}, status=status.HTTP_200_OK)
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
