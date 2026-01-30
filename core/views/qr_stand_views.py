from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.core.paginator import Paginator
import json
from decimal import Decimal
from ..models import QRStandOrder, User, SuperSetting
from ..serializers import QRStandOrderSerializer


@api_view(['GET'])
def qr_stand_order_list(request):
    """List QR stand orders (filtered by role)"""
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
        vendor_id = request.GET.get('vendor_id')
        order_status = request.GET.get('order_status')
        payment_status = request.GET.get('payment_status')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Filter by user - superusers can see all orders and filter by vendor_id
        if request.user.is_superuser:
            queryset = QRStandOrder.objects.all()
            if vendor_id:
                try:
                    queryset = queryset.filter(vendor_id=int(vendor_id))
                except ValueError:
                    pass
        else:
            # Regular users only see their own orders
            queryset = QRStandOrder.objects.filter(vendor=request.user)
        
        # Apply filters
        if order_status:
            queryset = queryset.filter(order_status=order_status)
        
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)
        
        # Apply search filter
        if search:
            queryset = queryset.filter(
                Q(vendor__name__icontains=search) | Q(vendor__phone__icontains=search)
            )
        
        # Apply date filters
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)
        
        # Order by created_at
        queryset = queryset.order_by('-created_at')
        
        # Paginate
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages
        
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1
        
        page_obj = paginator.get_page(page)
        
        serializer = QRStandOrderSerializer(page_obj, many=True, context={'request': request})
        
        return Response({
            'orders': serializer.data,
            'count': paginator.count,
            'page': page,
            'total_pages': total_pages,
            'page_size': page_size
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def qr_stand_order_create(request):
    """Create new QR stand order"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        # Get vendor - superusers can create orders for any vendor
        if request.user.is_superuser:
            vendor_id = data.get('vendor_id')
            if not vendor_id:
                return Response(
                    {'error': 'vendor_id is required for superusers'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            try:
                vendor = User.objects.get(id=int(vendor_id))
            except User.DoesNotExist:
                return Response(
                    {'error': 'Vendor not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # Regular users create orders for themselves
            vendor = request.user
        
        # Get quantity
        quantity = data.get('quantity')
        if not quantity:
            return Response(
                {'error': 'quantity is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            quantity = int(quantity)
            if quantity <= 0:
                return Response(
                    {'error': 'quantity must be greater than 0'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except ValueError:
            return Response(
                {'error': 'quantity must be a valid integer'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get price per QR stand from settings
        setting = SuperSetting.objects.first()
        per_qr_stand_price = setting.per_qr_stand_price if setting else 0
        
        if per_qr_stand_price == 0:
            return Response(
                {'error': 'QR stand price not configured. Please contact administrator.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate total price
        total_price = Decimal(quantity) * Decimal(per_qr_stand_price)
        
        # Create order
        order = QRStandOrder.objects.create(
            vendor=vendor,
            quantity=quantity,
            total_price=total_price,
            order_status='pending',
            payment_status='pending'
        )
        
        serializer = QRStandOrderSerializer(order, context={'request': request})
        return Response({
            'message': 'QR stand order created successfully',
            'order': serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def qr_stand_order_detail(request, id):
    """Get QR stand order details"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        order = QRStandOrder.objects.get(id=id)
        
        # Check permissions - superusers can see all, others only their own
        if not request.user.is_superuser and order.vendor != request.user:
            return Response(
                {'error': 'You do not have permission to view this order'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = QRStandOrderSerializer(order, context={'request': request})
        return Response({
            'order': serializer.data
        }, status=status.HTTP_200_OK)
        
    except QRStandOrder.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT'])
def qr_stand_order_update(request, id):
    """Update QR stand order status"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        order = QRStandOrder.objects.get(id=id)
        
        # Check permissions - superusers can update all, others only their own
        if not request.user.is_superuser and order.vendor != request.user:
            return Response(
                {'error': 'You do not have permission to update this order'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        # Update fields if provided
        if 'order_status' in data:
            order_status = data.get('order_status')
            if order_status in [choice[0] for choice in QRStandOrder.STATUS_CHOICES]:
                order.order_status = order_status
        
        if 'payment_status' in data:
            payment_status = data.get('payment_status')
            if payment_status in [choice[0] for choice in QRStandOrder.PAYMENT_STATUS_CHOICES]:
                order.payment_status = payment_status
        
        if 'quantity' in data:
            quantity = data.get('quantity')
            try:
                quantity = int(quantity)
                if quantity > 0:
                    # Recalculate total price
                    setting = SuperSetting.objects.first()
                    per_qr_stand_price = setting.per_qr_stand_price if setting else 0
                    order.quantity = quantity
                    order.total_price = Decimal(quantity) * Decimal(per_qr_stand_price)
            except ValueError:
                pass  # Ignore invalid quantity
        
        order.save()
        
        serializer = QRStandOrderSerializer(order, context={'request': request})
        return Response({
            'message': 'Order updated successfully',
            'order': serializer.data
        }, status=status.HTTP_200_OK)
        
    except QRStandOrder.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
def qr_stand_order_delete(request, id):
    """Delete QR stand order (super admin only)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can delete orders'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        order = QRStandOrder.objects.get(id=id)
        order.delete()
        
        return Response({
            'message': 'Order deleted successfully'
        }, status=status.HTTP_200_OK)
        
    except QRStandOrder.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
