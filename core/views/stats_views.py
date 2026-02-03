from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Sum, Q
from django.utils import timezone
from ..models import Product, Order, OrderItem, Category, TransactionHistory, Unit, User, SuperSetting, QRStandOrder
from decimal import Decimal


@api_view(['GET'])
def product_stats(request):
    """Get product statistics"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user_id = request.GET.get('user_id')
        
        # Filter by user - superusers can see all products and filter by user_id
        if request.user.is_superuser:
            queryset = Product.objects.all()
            if user_id:
                try:
                    queryset = queryset.filter(user_id=int(user_id))
                except ValueError:
                    pass
        else:
            queryset = Product.objects.filter(user=request.user)
        
        total = queryset.count()
        active = queryset.filter(is_active=True).count()
        inactive = queryset.filter(is_active=False).count()
        
        # Products by category
        by_category = queryset.values('category__name').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Products by type
        by_type = queryset.values('type').annotate(
            count=Count('id')
        )
        
        # Top selling: count of distinct products (from this queryset) that appear in OrderItem
        product_ids = list(queryset.values_list('id', flat=True))
        top_selling = 0
        if product_ids:
            top_selling = OrderItem.objects.filter(
                product_id__in=product_ids
            ).values('product').distinct().count()
        
        return Response({
            'total': total,
            'active': active,
            'inactive': inactive,
            'top_selling': top_selling,
            'by_category': list(by_category),
            'by_type': list(by_type)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def order_stats(request):
    """Get order statistics"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user_id = request.GET.get('user_id')
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
        
        # Apply date filters
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        total = queryset.count()
        
        # Orders by status (flat keys for frontend)
        by_status = queryset.values('status').annotate(count=Count('id'))
        status_map = {row['status']: row['count'] for row in by_status}
        pending = status_map.get('pending', 0)
        accepted = status_map.get('accepted', 0)
        running = status_map.get('running', 0)
        ready = status_map.get('ready', 0)
        rejected = status_map.get('rejected', 0)
        completed = status_map.get('completed', 0)
        
        # Orders by payment status
        by_payment_status = queryset.values('payment_status').annotate(
            count=Count('id')
        )
        
        # Total revenue
        revenue = queryset.aggregate(
            total_revenue=Sum('total')
        )['total_revenue'] or Decimal('0')
        
        # Paid orders revenue
        paid_revenue = queryset.filter(payment_status='paid').aggregate(
            total_revenue=Sum('total')
        )['total_revenue'] or Decimal('0')
        
        return Response({
            'total': total,
            'revenue': str(revenue),
            'paid_revenue': str(paid_revenue),
            'pending': pending,
            'accepted': accepted,
            'running': running,
            'ready': ready,
            'rejected': rejected,
            'completed': completed,
            'by_status': list(by_status),
            'by_payment_status': list(by_payment_status)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def category_stats(request):
    """Get category statistics"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user_id = request.GET.get('user_id')
        
        # Filter by user - superusers can see all categories and filter by user_id
        if request.user.is_superuser:
            queryset = Category.objects.all()
            if user_id:
                try:
                    queryset = queryset.filter(user_id=int(user_id))
                except ValueError:
                    pass
        else:
            queryset = Category.objects.filter(user=request.user)
        
        total = queryset.count()
        
        # Products per category
        products_per_category = queryset.annotate(
            product_count=Count('products')
        ).values('id', 'name', 'product_count').order_by('-product_count')
        
        return Response({
            'total': total,
            'products_per_category': list(products_per_category)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def transaction_stats(request):
    """Get transaction statistics"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user_id = request.GET.get('user_id')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Filter by user - superusers can see all transactions and filter by user_id
        if request.user.is_superuser:
            queryset = TransactionHistory.objects.all()
            if user_id:
                try:
                    queryset = queryset.filter(user_id=int(user_id))
                except ValueError:
                    pass
        else:
            queryset = TransactionHistory.objects.filter(user=request.user)
        
        # Apply date filters (align with list when frontend passes them)
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        total = queryset.count()
        
        # Status counts (flat keys for frontend)
        by_status = queryset.values('status').annotate(count=Count('id'))
        status_map = {row['status']: row['count'] for row in by_status}
        pending = status_map.get('pending', 0)
        success = status_map.get('success', 0)
        failed = status_map.get('failed', 0)
        
        # Total revenue (successful transactions)
        revenue = queryset.filter(status='success').aggregate(
            total_revenue=Sum('amount')
        )['total_revenue'] or Decimal('0')
        
        # Category counts (transaction_category)
        by_category = queryset.values('transaction_category').annotate(count=Count('id'))
        cat_map = {row['transaction_category']: row['count'] for row in by_category}
        
        return Response({
            'total': total,
            'total_revenue': str(revenue),
            'revenue': str(revenue),
            'pending': pending,
            'success': success,
            'failed': failed,
            'order': cat_map.get('order', 0),
            'transaction_fee': cat_map.get('transaction_fee', 0),
            'subscription_payments': cat_map.get('subscription_fee', 0),
            'whatsapp_usage': cat_map.get('whatsapp_usage', 0),
            'qr_stand_orders': cat_map.get('qr_stand_order', 0),
            'due_payments': cat_map.get('due_paid', 0),
            'share_distributions': cat_map.get('share_distribution', 0),
            'shareholder_withdrawals': cat_map.get('share_withdrawal', 0),
            'by_status': list(queryset.values('status').annotate(count=Count('id'), total_amount=Sum('amount'))),
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def unit_stats(request):
    """Get unit statistics"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user_id = request.GET.get('user_id')
        
        # Filter by user - superusers can see all units and filter by user_id
        if request.user.is_superuser:
            queryset = Unit.objects.all()
            if user_id:
                try:
                    queryset = queryset.filter(user_id=int(user_id))
                except ValueError:
                    pass
        else:
            queryset = Unit.objects.filter(user=request.user)
        
        total = queryset.count()
        
        return Response({
            'total': total
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def vendor_stats(request):
    """Get vendor statistics - superuser only"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only superusers can view vendor statistics'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Vendors only (exclude superusers from vendor counts)
        queryset = User.objects.filter(is_superuser=False)
        
        total = queryset.count()
        active = queryset.filter(is_active=True).count()
        inactive = queryset.filter(is_active=False).count()
        superusers = User.objects.filter(is_superuser=True).count()
        
        # KYC and subscription
        kyc_pending = queryset.filter(kyc_status=User.KYC_PENDING).count()
        today = timezone.now().date()
        subscription_expired = queryset.filter(
            subscription_end_date__lt=today,
            subscription_end_date__isnull=False
        ).count()
        
        # Due balance
        due_agg = queryset.aggregate(total_due=Sum('due_balance'))
        total_due_amount = due_agg['total_due'] or 0
        setting = SuperSetting.objects.filter(id=1).first()
        due_threshold = getattr(setting, 'due_threshold', 1000) if setting else 1000
        due_blocked_vendors = queryset.filter(due_balance__gte=due_threshold).count()
        
        return Response({
            'total': total,
            'active': active,
            'inactive': inactive,
            'superusers': superusers,
            'kyc_pending': kyc_pending,
            'subscription_expired': subscription_expired,
            'total_due_amount': total_due_amount,
            'due_blocked_vendors': due_blocked_vendors,
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def vendor_stats_by_id(request, id):
    """Get per-vendor statistics. Vendor can see own; superuser can see any."""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    if request.user.id != id and not request.user.is_superuser:
        return Response(
            {'error': 'You can only view your own vendor statistics'},
            status=status.HTTP_403_FORBIDDEN
        )
    try:
        try:
            vendor = User.objects.get(id=id)
        except User.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        # Transaction counts/amounts for this vendor
        txn_qs = TransactionHistory.objects.filter(user=vendor)
        whatsapp_count = txn_qs.filter(transaction_category='whatsapp_usage').count()
        txn_fee_agg = txn_qs.filter(transaction_category='transaction_fee').aggregate(s=Sum('amount'))
        sub_fee_agg = txn_qs.filter(transaction_category='subscription_fee').aggregate(s=Sum('amount'))
        transaction_fee = (txn_fee_agg['s'] or Decimal('0'))
        subscription_fee = (sub_fee_agg['s'] or Decimal('0'))
        # Orders
        order_qs = Order.objects.filter(user=vendor)
        total_orders = order_qs.count()
        total_revenue_agg = order_qs.aggregate(s=Sum('total'))
        total_revenue = (total_revenue_agg['s'] or Decimal('0'))
        # QR stand
        qr_qs = QRStandOrder.objects.filter(vendor=vendor)
        qr_stand_orders = qr_qs.count()
        qr_pending_orders = qr_qs.filter(order_status='pending').count()
        return Response({
            'whatsapp_usage': whatsapp_count,
            'transaction_fee': str(transaction_fee),
            'subscription_fee': str(subscription_fee),
            'qr_stand_orders': qr_stand_orders,
            'qr_pending_orders': qr_pending_orders,
            'total_orders': total_orders,
            'total_revenue': str(total_revenue),
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def qr_stand_stats(request):
    """Get QR stand order statistics. Vendors see own; superuser sees all."""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        if request.user.is_superuser:
            queryset = QRStandOrder.objects.all()
        else:
            queryset = QRStandOrder.objects.filter(vendor=request.user)

        total = queryset.count()
        pending = queryset.filter(order_status='pending').count()
        accepted = queryset.filter(order_status__in=['accepted', 'saved']).count()
        delivered = queryset.filter(order_status='delivered').count()
        revenue = queryset.filter(payment_status='paid').aggregate(
            total_revenue=Sum('total_price')
        )['total_revenue'] or Decimal('0')

        return Response({
            'total': total,
            'pending': pending,
            'accepted': accepted,
            'delivered': delivered,
            'revenue': str(revenue),
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
