from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import json
from decimal import Decimal
from django.db.models import Q
from django.core.paginator import Paginator
from ..models import Order, OrderItem, Product, ProductVariant, User
from ..serializers import OrderSerializer, OrderItemSerializer
from ..services.fcm_service import send_fcm_notification


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
        table_no = data.get('table_no')
        status_val = data.get('status', 'pending')
        payment_status = data.get('payment_status', 'pending')
        fcm_token = data.get('fcm_token', '')
        items_data = data.get('items', '[]')
        total = data.get('total', '0')
        vendor_phone = data.get('vendor_phone')
        
        if not name or not phone or not table_no:
            return Response(
                {'error': 'Name, phone, and table_no are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Determine the vendor/user for this order
        order_user = None
        if request.user.is_authenticated:
            # Authenticated user - use their account
            order_user = request.user
        elif vendor_phone:
            # Guest order - find vendor by phone
            try:
                order_user = User.objects.get(phone=vendor_phone, is_active=True)
            except User.DoesNotExist:
                return Response(
                    {'error': 'Vendor not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            return Response(
                {'error': 'Either authentication or vendor_phone is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create order
        order = Order.objects.create(
            name=name,
            phone=phone,
            table_no=table_no,
            status=status_val,
            payment_status=payment_status,
            total=Decimal(str(total)),
            fcm_token=fcm_token,
            user=order_user
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
        
        # Send FCM notification if token is provided and status is pending
        if fcm_token and status_val == 'pending':
            try:
                # Ensure all data values are strings (required for FCM)
                send_fcm_notification(
                    fcm_token=fcm_token,
                    title='Order Placed',
                    body='Your Order is Pending right now wait for accept from kitchen',
                    data={
                        'order_id': str(order.id),
                        'status': str(status_val)
                    }
                )
            except Exception as e:
                # Log error but don't fail the order creation
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f'Failed to send FCM notification: {str(e)}')
        
        serializer = OrderSerializer(order, context={'request': request})
        return Response({'order': serializer.data}, status=status.HTTP_201_CREATED)
        
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
    """Update an order"""
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
        
        name = request.POST.get('name')
        phone = request.POST.get('phone')
        table_no = request.POST.get('table_no')
        status_val = request.POST.get('status')
        payment_status = request.POST.get('payment_status')
        fcm_token = request.POST.get('fcm_token')
        items_data = request.POST.get('items')
        total = request.POST.get('total')
        reject_reason = request.POST.get('reject_reason')
        
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
        
        # Send FCM notification if status changed and fcm_token exists
        if status_val and status_val != old_status and order.fcm_token:
            try:
                # Map status to notification messages
                status_messages = {
                    'pending': {
                        'title': 'Order Status Update',
                        'body': 'Your Order is Pending right now wait for accept from kitchen'
                    },
                    'accepted': {
                        'title': 'Order Accepted',
                        'body': f'Your Order #{order.id} has been accepted and is being prepared'
                    },
                    'rejected': {
                        'title': 'Order Rejected',
                        'body': f'Your Order #{order.id} has been rejected' + (f': {order.reject_reason}' if order.reject_reason else '')
                    },
                    'completed': {
                        'title': 'Order Completed',
                        'body': f'Your Order #{order.id} is ready! Please collect from table {order.table_no}'
                    }
                }
                
                message = status_messages.get(status_val, {
                    'title': 'Order Status Update',
                    'body': f'Your Order #{order.id} status has been updated to {status_val}'
                })
                
                # Ensure all data values are strings (required for FCM)
                send_fcm_notification(
                    fcm_token=order.fcm_token,
                    title=message['title'],
                    body=message['body'],
                    data={
                        'order_id': str(order.id),
                        'status': str(status_val),
                        'table_no': str(order.table_no)
                    }
                )
            except Exception as e:
                # Log error but don't fail the order update
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f'Failed to send FCM notification for order {order.id}: {str(e)}')
        
        # Update items if provided
        if items_data:
            try:
                # Delete existing items
                OrderItem.objects.filter(order=order).delete()
                
                # Create new items
                items_list = json.loads(items_data) if isinstance(items_data, str) else items_data
                for item_data in items_list:
                    product_id = item_data.get('product_id')
                    product_variant_id = item_data.get('product_variant_id')
                    quantity = item_data.get('quantity', 1)
                    price = item_data.get('price', '0')
                    
                    if product_id and product_variant_id:
                        try:
                            product = Product.objects.get(id=product_id, user=request.user)
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


@api_view(['GET'])
def order_delete(request, id):
    """Delete an order"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can delete any order, regular users only their own
        if request.user.is_superuser:
            order = Order.objects.get(id=id)
        else:
            order = Order.objects.get(id=id, user=request.user)
        order.delete()
        return Response({'message': 'Order deleted successfully'}, status=status.HTTP_200_OK)
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
