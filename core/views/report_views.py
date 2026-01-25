from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Sum, Q, Avg
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta
from ..models import Product, Order, Category, TransactionHistory, OrderItem, User


@api_view(['GET'])
def cafe_report(request):
    """Get comprehensive cafe report"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user_id = request.GET.get('user_id')
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        # Filter by user - superusers can see all data and filter by user_id
        if request.user.is_superuser:
            if user_id:
                try:
                    user_filter = {'user_id': int(user_id)}
                except ValueError:
                    user_filter = {}
            else:
                user_filter = {}
        else:
            user_filter = {'user': request.user}
        
        # Set default date range to last 7 days if not provided
        if not start_date_str or not end_date_str:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=6)  # 7 days including today
        else:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Orders in date range
        orders_queryset = Order.objects.filter(**user_filter).filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        
        # Summary statistics
        total_orders = orders_queryset.count()
        total_revenue = orders_queryset.aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        paid_orders = orders_queryset.filter(payment_status='paid').count()
        paid_revenue = orders_queryset.filter(payment_status='paid').aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        # Orders by status
        orders_by_status = orders_queryset.values('status').annotate(
            count=Count('id'),
            revenue=Sum('total')
        )
        
        # Orders by payment status
        orders_by_payment_status = orders_queryset.values('payment_status').annotate(
            count=Count('id'),
            revenue=Sum('total')
        )
        
        # Products statistics
        products_count = Product.objects.filter(**user_filter).count()
        categories_count = Category.objects.filter(**user_filter).count()
        
        # Top products
        top_products = OrderItem.objects.filter(
            order__in=orders_queryset.values_list('id', flat=True)
        ).values(
            'product__name', 'product__category__name'
        ).annotate(
            total_revenue=Sum('total'),
            total_quantity=Sum('quantity'),
            order_count=Count('order', distinct=True)
        ).order_by('-total_revenue')[:20]
        
        # Revenue by category
        revenue_by_category = OrderItem.objects.filter(
            order__in=orders_queryset.values_list('id', flat=True)
        ).values(
            'product__category__name'
        ).annotate(
            total_revenue=Sum('total'),
            order_count=Count('order', distinct=True)
        ).order_by('-total_revenue')
        
        # Daily breakdown
        daily_breakdown = []
        current_date = start_date
        while current_date <= end_date:
            day_orders = orders_queryset.filter(created_at__date=current_date)
            day_revenue = day_orders.aggregate(total=Sum('total'))['total'] or Decimal('0')
            daily_breakdown.append({
                'date': current_date.isoformat(),
                'orders': day_orders.count(),
                'revenue': str(day_revenue)
            })
            current_date += timedelta(days=1)
        
        # Detailed orders list
        detailed_orders = orders_queryset.order_by('-created_at').values(
            'id', 'name', 'phone', 'table_no', 'status', 'payment_status', 
            'total', 'created_at'
        )
        
        return Response({
            'summary': {
                'total_orders': total_orders,
                'total_revenue': str(total_revenue),
                'paid_orders': paid_orders,
                'paid_revenue': str(paid_revenue),
                'products_count': products_count,
                'categories_count': categories_count
            },
            'orders_by_status': list(orders_by_status),
            'orders_by_payment_status': list(orders_by_payment_status),
            'top_products': list(top_products),
            'revenue_by_category': list(revenue_by_category),
            'daily_breakdown': daily_breakdown,
            'detailed_orders': list(detailed_orders)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def order_report(request):
    """Get order report"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user_id = request.GET.get('user_id')
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        # Filter by user - superusers can see all data and filter by user_id
        if request.user.is_superuser:
            if user_id:
                try:
                    user_filter = {'user_id': int(user_id)}
                except ValueError:
                    user_filter = {}
            else:
                user_filter = {}
        else:
            user_filter = {'user': request.user}
        
        # Set default date range to last 7 days if not provided
        if not start_date_str or not end_date_str:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=6)  # 7 days including today
        else:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Orders in date range
        orders_queryset = Order.objects.filter(**user_filter).filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        
        # Summary
        total_orders = orders_queryset.count()
        total_revenue = orders_queryset.aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        # Orders by status with details
        orders_by_status = orders_queryset.values('status').annotate(
            count=Count('id'),
            revenue=Sum('total'),
            avg_order_value=Avg('total')
        )
        
        # Orders by payment status
        orders_by_payment_status = orders_queryset.values('payment_status').annotate(
            count=Count('id'),
            revenue=Sum('total')
        )
        
        # Detailed orders with items
        detailed_orders = []
        for order in orders_queryset.select_related('user').prefetch_related('items__product', 'items__product_variant').order_by('-created_at'):
            order_items = order.items.all()
            detailed_orders.append({
                'id': order.id,
                'name': order.name,
                'phone': order.phone,
                'table_no': order.table_no,
                'status': order.status,
                'payment_status': order.payment_status,
                'total': str(order.total),
                'created_at': order.created_at.isoformat(),
                'items': [{
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'price': str(item.price),
                    'total': str(item.total)
                } for item in order_items]
            })
        
        return Response({
            'summary': {
                'total_orders': total_orders,
                'total_revenue': str(total_revenue),
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'orders_by_status': list(orders_by_status),
            'orders_by_payment_status': list(orders_by_payment_status),
            'detailed_orders': detailed_orders
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def product_report(request):
    """Get product report"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user_id = request.GET.get('user_id')
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        # Filter by user - superusers can see all data and filter by user_id
        if request.user.is_superuser:
            if user_id:
                try:
                    user_filter = {'user_id': int(user_id)}
                except ValueError:
                    user_filter = {}
            else:
                user_filter = {}
        else:
            user_filter = {'user': request.user}
        
        # Set default date range to last 7 days if not provided
        if not start_date_str or not end_date_str:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=6)  # 7 days including today
        else:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Orders in date range
        orders_queryset = Order.objects.filter(**user_filter).filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        
        # Product sales statistics
        product_stats = OrderItem.objects.filter(
            order__in=orders_queryset.values_list('id', flat=True)
        ).values(
            'product__id',
            'product__name',
            'product__category__name',
            'product__type'
        ).annotate(
            total_revenue=Sum('total'),
            total_quantity=Sum('quantity'),
            order_count=Count('order', distinct=True),
            avg_price=Avg('price')
        ).order_by('-total_revenue')
        
        # Products by category
        products_by_category = OrderItem.objects.filter(
            order__in=orders_queryset.values_list('id', flat=True)
        ).values(
            'product__category__name'
        ).annotate(
            product_count=Count('product', distinct=True),
            total_revenue=Sum('total'),
            total_quantity=Sum('quantity')
        ).order_by('-total_revenue')
        
        # Top selling products
        top_products = list(product_stats[:20])
        
        # Summary
        total_products_sold = product_stats.count()
        total_revenue = sum(Decimal(str(p['total_revenue'])) for p in product_stats)
        total_quantity = sum(p['total_quantity'] for p in product_stats)
        
        return Response({
            'summary': {
                'total_products_sold': total_products_sold,
                'total_revenue': str(total_revenue),
                'total_quantity': total_quantity,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'products_by_category': list(products_by_category),
            'top_products': top_products,
            'all_products': list(product_stats)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def finance_report(request):
    """Get financial report"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user_id = request.GET.get('user_id')
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        # Filter by user - superusers can see all data and filter by user_id
        if request.user.is_superuser:
            if user_id:
                try:
                    user_filter = {'user_id': int(user_id)}
                except ValueError:
                    user_filter = {}
            else:
                user_filter = {}
        else:
            user_filter = {'user': request.user}
        
        # Set default date range to last 7 days if not provided
        if not start_date_str or not end_date_str:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=6)  # 7 days including today
        else:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Orders in date range
        orders_queryset = Order.objects.filter(**user_filter).filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        
        # Transactions in date range
        transactions_queryset = TransactionHistory.objects.filter(**user_filter).filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        
        # Order revenue
        total_order_revenue = orders_queryset.aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        paid_order_revenue = orders_queryset.filter(payment_status='paid').aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        pending_order_revenue = orders_queryset.filter(payment_status='pending').aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        # Transaction statistics
        total_transactions = transactions_queryset.count()
        successful_transactions = transactions_queryset.filter(status='success')
        total_transaction_amount = successful_transactions.aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        # Transactions by status
        transactions_by_status = transactions_queryset.values('status').annotate(
            count=Count('id'),
            total_amount=Sum('amount')
        )
        
        # Daily financial breakdown
        daily_breakdown = []
        current_date = start_date
        while current_date <= end_date:
            day_orders = orders_queryset.filter(created_at__date=current_date)
            day_transactions = transactions_queryset.filter(created_at__date=current_date)
            
            day_order_revenue = day_orders.aggregate(total=Sum('total'))['total'] or Decimal('0')
            day_transaction_amount = day_transactions.filter(status='success').aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')
            
            daily_breakdown.append({
                'date': current_date.isoformat(),
                'order_revenue': str(day_order_revenue),
                'transaction_amount': str(day_transaction_amount),
                'orders_count': day_orders.count(),
                'transactions_count': day_transactions.count()
            })
            current_date += timedelta(days=1)
        
        # Detailed transactions
        detailed_transactions = transactions_queryset.order_by('-created_at').values(
            'id', 'order_id', 'amount', 'status', 'remarks', 'utr', 'vpa', 
            'payer_name', 'created_at'
        )
        
        return Response({
            'summary': {
                'total_order_revenue': str(total_order_revenue),
                'paid_order_revenue': str(paid_order_revenue),
                'pending_order_revenue': str(pending_order_revenue),
                'total_transactions': total_transactions,
                'total_transaction_amount': str(total_transaction_amount),
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'transactions_by_status': list(transactions_by_status),
            'daily_breakdown': daily_breakdown,
            'detailed_transactions': list(detailed_transactions)
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
