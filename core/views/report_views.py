from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Sum, Q, Avg, Max, Min
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta
from ..models import (
    Product, Order, Category, TransactionHistory, OrderItem, User,
    SuperSetting, ShareholderWithdrawal,
)
from ..utils.subscription_helpers import get_effective_subscription_end_date
from ..utils.date_helpers import parse_date_range


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

        # Orders in date range (00:01 start, 23:59:59 end of selected dates)
        orders_queryset = Order.objects.filter(**user_filter)
        date_range = parse_date_range(start_date.isoformat(), end_date.isoformat())
        if date_range:
            start_dt, end_dt = date_range
            orders_queryset = orders_queryset.filter(created_at__gte=start_dt, created_at__lte=end_dt)
        
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

        # Orders in date range (00:01 start, 23:59:59 end of selected dates)
        orders_queryset = Order.objects.filter(**user_filter)
        date_range = parse_date_range(start_date.isoformat(), end_date.isoformat())
        if date_range:
            start_dt, end_dt = date_range
            orders_queryset = orders_queryset.filter(created_at__gte=start_dt, created_at__lte=end_dt)
        
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
        
        # Daily breakdown for charts
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
        
        # Detailed orders with items
        detailed_orders = []
        for order in orders_queryset.select_related('user').prefetch_related('items__product', 'items__product_variant').order_by('-created_at'):
            order_items = order.items.all()
            detailed_orders.append({
                'id': order.id,
                'name': order.name,
                'phone': order.phone,
                'table_no': order.table_no or '',
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
            'daily_breakdown': daily_breakdown,
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

        # Orders in date range (00:01 start, 23:59:59 end of selected dates)
        orders_queryset = Order.objects.filter(**user_filter)
        date_range = parse_date_range(start_date.isoformat(), end_date.isoformat())
        if date_range:
            start_dt, end_dt = date_range
            orders_queryset = orders_queryset.filter(created_at__gte=start_dt, created_at__lte=end_dt)
        
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

        # Orders and transactions in date range (00:01 start, 23:59:59 end of selected dates)
        orders_queryset = Order.objects.filter(**user_filter)
        transactions_queryset = TransactionHistory.objects.filter(**user_filter)
        date_range = parse_date_range(start_date.isoformat(), end_date.isoformat())
        if date_range:
            start_dt, end_dt = date_range
            orders_queryset = orders_queryset.filter(created_at__gte=start_dt, created_at__lte=end_dt)
            transactions_queryset = transactions_queryset.filter(created_at__gte=start_dt, created_at__lte=end_dt)
        # Hide whole UG payment rows from vendor
        if not request.user.is_superuser:
            transactions_queryset = transactions_queryset.exclude(
                Q(remarks__icontains='ug payment') | Q(ug_client_txn_id__isnull=False)
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
        detailed_transactions = list(transactions_queryset.order_by('-created_at').values(
            'id', 'order_id', 'amount', 'status', 'remarks', 'utr', 'vpa', 
            'payer_name', 'created_at'
        ))
        
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
            'detailed_transactions': detailed_transactions
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def vendor_report(request):
    """Get vendor report (superuser only). Returns vendor list, stats, and chart data."""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can access this report'},
            status=status.HTTP_403_FORBIDDEN
        )
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                start_date = end_date = timezone.now().date()
        else:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=29)
        date_range = parse_date_range(start_date.isoformat(), end_date.isoformat())
        start_dt, end_dt = date_range if date_range else (None, None)
        vendors_qs = User.objects.filter(is_superuser=False).order_by('-id')
        setting = SuperSetting.objects.first()
        due_threshold = getattr(setting, 'due_threshold', 1000) if setting else 1000
        today = timezone.now().date()
        total_vendors = vendors_qs.count()
        active_vendors = vendors_qs.filter(is_active=True).count()
        inactive_vendors = vendors_qs.filter(is_active=False).count()
        pending_kyc_vendors = vendors_qs.filter(kyc_status=User.KYC_PENDING).count()
        # Effective end date = expire_date or subscription_end_date
        expired_vendors = vendors_qs.filter(
            Q(expire_date__lt=today, expire_date__isnull=False) |
            Q(expire_date__isnull=True, subscription_end_date__lt=today, subscription_end_date__isnull=False)
        ).count()
        due_blocked_vendors = vendors_qs.filter(due_balance__gte=due_threshold).count()
        orders_in_period = Order.objects.filter(user__in=vendors_qs)
        if start_dt is not None and end_dt is not None:
            orders_in_period = orders_in_period.filter(created_at__gte=start_dt, created_at__lte=end_dt)
        total_vendor_revenue = orders_in_period.aggregate(total=Sum('total'))['total'] or Decimal('0')
        total_due_amount = vendors_qs.aggregate(s=Sum('due_balance'))['s'] or 0
        vendors_by_status = [
            {'status': 'active', 'count': active_vendors},
            {'status': 'inactive', 'count': inactive_vendors},
            {'status': 'pending_kyc', 'count': pending_kyc_vendors},
            {'status': 'expired', 'count': expired_vendors},
            {'status': 'due_blocked', 'count': due_blocked_vendors},
        ]
        top_vendors_revenue_qs = Order.objects.all()
        if start_dt is not None and end_dt is not None:
            top_vendors_revenue_qs = top_vendors_revenue_qs.filter(created_at__gte=start_dt, created_at__lte=end_dt)
        top_vendors_revenue = (
            top_vendors_revenue_qs
            .values('user_id')
            .annotate(total_revenue=Sum('total'), total_orders=Count('id'))
            .order_by('-total_revenue')[:15]
        )
        user_ids = [v['user_id'] for v in top_vendors_revenue if v['user_id']]
        users_map = {u.id: u for u in User.objects.filter(id__in=user_ids)}
        top_vendors_list = []
        for v in top_vendors_revenue:
            u = users_map.get(v['user_id'])
            if u:
                logo_url = request.build_absolute_uri(u.logo.url) if u.logo else None
                top_vendors_list.append({
                    'id': u.id,
                    'name': u.name,
                    'phone': u.phone,
                    'logo_url': logo_url,
                    'total_revenue': int(Decimal(str(v['total_revenue'] or 0))),
                    'total_orders': v['total_orders'],
                })
        from django.db.models.functions import TruncDate
        registration_over_time = list(
            User.objects.filter(is_superuser=False)
            .annotate(created_date=TruncDate('created_at'))
            .values('created_date')
            .annotate(count=Count('id'))
            .order_by('created_date')
        )
        vendors_list = []
        for v in vendors_qs.order_by('-id')[:200]:
            last_order = Order.objects.filter(user=v).order_by('-created_at').first()
            total_orders = Order.objects.filter(user=v).count()
            rev = Order.objects.filter(user=v).aggregate(t=Sum('total'))['t'] or Decimal('0')
            logo_url = request.build_absolute_uri(v.logo.url) if v.logo else None
            effective_end = get_effective_subscription_end_date(v)
            vendors_list.append({
                'id': v.id,
                'name': v.name,
                'phone': v.phone,
                'country_code': v.country_code or '91',
                'logo_url': logo_url,
                'kyc_status': v.kyc_status,
                'subscription_end_date': effective_end.isoformat() if effective_end else None,
                'due_balance': v.due_balance,
                'is_over_threshold': v.due_balance >= due_threshold,
                'total_orders': total_orders,
                'total_revenue': str(rev),
                'last_order_date': last_order.created_at.date().isoformat() if last_order else None,
                'is_active': v.is_active,
                'created_at': v.created_at.isoformat() if v.created_at else None,
            })
        over_dues_list = [x for x in vendors_list if x['is_over_threshold']]
        return Response({
            'summary': {
                'total_vendors': total_vendors,
                'active_vendors': active_vendors,
                'inactive_vendors': inactive_vendors,
                'pending_kyc_vendors': pending_kyc_vendors,
                'expired_vendors': expired_vendors,
                'due_blocked_vendors': due_blocked_vendors,
                'total_vendor_revenue': str(total_vendor_revenue),
                'total_due_amount': total_due_amount,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
            },
            'vendors_by_status': vendors_by_status,
            'top_vendors_by_revenue': top_vendors_list,
            'vendor_registration_over_time': registration_over_time,
            'vendors_list': vendors_list,
            'over_dues_list': over_dues_list,
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def shareholder_report(request):
    """Get shareholder report (superuser only)."""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can access this report'},
            status=status.HTTP_403_FORBIDDEN
        )
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                start_date = end_date = timezone.now().date()
        else:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=89)
        date_range = parse_date_range(start_date.isoformat(), end_date.isoformat())
        start_dt, end_dt = date_range if date_range else (None, None)
        shareholders = User.objects.filter(is_shareholder=True).order_by('-share_percentage')
        setting = SuperSetting.objects.first()
        next_distribution_day = getattr(setting, 'share_distribution_day', 7) if setting else 7
        total_shareholders = shareholders.count()
        total_shareholder_balance = sum(s.balance for s in shareholders)
        total_distributed_qs = TransactionHistory.objects.filter(
            transaction_category='share_distribution',
            status='success'
        )
        if start_dt is not None and end_dt is not None:
            total_distributed_qs = total_distributed_qs.filter(created_at__gte=start_dt, created_at__lte=end_dt)
        total_distributed = total_distributed_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        total_withdrawals = ShareholderWithdrawal.objects.filter(
            status='approved'
        ).aggregate(t=Sum('amount'))['t'] or 0
        pending_withdrawals_count = ShareholderWithdrawal.objects.filter(status='pending').count()
        pending_withdrawals_amount = ShareholderWithdrawal.objects.filter(
            status='pending'
        ).aggregate(t=Sum('amount'))['t'] or 0
        shareholder_distribution = []
        for s in shareholders:
            logo_url = request.build_absolute_uri(s.logo.url) if s.logo else None
            shareholder_distribution.append({
                'id': s.id,
                'name': s.name,
                'phone': s.phone,
                'share_percentage': s.share_percentage,
                'amount': int((total_shareholder_balance * s.share_percentage) / 100) if total_shareholder_balance else 0,
                'balance': s.balance,
                'logo_url': logo_url,
            })
        dist_txns = TransactionHistory.objects.filter(
            transaction_category='share_distribution',
            status='success'
        ).extra(select={'d': 'date(created_at)'}).values('d').annotate(
            total=Sum('amount'), count=Count('id')
        ).order_by('d')
        distribution_over_time = [{'date': str(x['d']), 'total': str(x['total']), 'count': x['count']} for x in dist_txns]
        wot = list(
            ShareholderWithdrawal.objects.filter(status='approved')
            .extra(select={'d': 'date(created_at)'})
            .values('d')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('d')
        )
        withdrawals_over_time = [{'date': str(x['d']), 'total': x['total'], 'count': x['count']} for x in wot]
        shareholders_list = []
        for s in shareholders:
            received = TransactionHistory.objects.filter(
                user=s, transaction_category='share_distribution', status='success'
            ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
            withdrawn = ShareholderWithdrawal.objects.filter(user=s, status='approved').aggregate(
                t=Sum('amount')
            )['t'] or 0
            logo_url = request.build_absolute_uri(s.logo.url) if s.logo else None
            shareholders_list.append({
                'id': s.id,
                'name': s.name,
                'phone': s.phone,
                'country_code': s.country_code or '91',
                'logo_url': logo_url,
                'share_percentage': s.share_percentage,
                'balance': s.balance,
                'total_received': str(received),
                'total_withdrawn': withdrawn,
                'created_at': s.created_at.isoformat() if s.created_at else None,
            })
        withdrawals_list = []
        for w in ShareholderWithdrawal.objects.select_related('user').order_by('-created_at')[:100]:
            u = w.user
            withdrawals_list.append({
                'id': w.id,
                'user_id': u.id,
                'user_name': u.name,
                'user_phone': u.phone,
                'amount': w.amount,
                'status': w.status,
                'remarks': w.remarks,
                'created_at': w.created_at.isoformat() if w.created_at else None,
                'updated_at': w.updated_at.isoformat() if w.updated_at else None,
            })
        dist_history = list(
            TransactionHistory.objects.filter(
                transaction_category='share_distribution',
                status='success'
            ).order_by('-created_at')[:50].values('id', 'user_id', 'amount', 'created_at')
        )
        dist_by_date = {}
        for t in dist_history:
            dt = t['created_at'].date().isoformat() if hasattr(t['created_at'], 'date') else str(t['created_at'])[:10]
            if dt not in dist_by_date:
                dist_by_date[dt] = {'date': dt, 'total': Decimal('0'), 'breakdown': []}
            dist_by_date[dt]['total'] += Decimal(str(t['amount']))
            dist_by_date[dt]['breakdown'].append({'user_id': t['user_id'], 'amount': str(t['amount'])})
        distribution_history = list(dist_by_date.values())
        return Response({
            'summary': {
                'total_shareholders': total_shareholders,
                'total_shareholder_balance': total_shareholder_balance,
                'total_distributed': str(total_distributed),
                'total_withdrawals': total_withdrawals,
                'pending_withdrawals_count': pending_withdrawals_count,
                'pending_withdrawals_amount': pending_withdrawals_amount or 0,
                'next_distribution_day': next_distribution_day,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
            },
            'shareholder_distribution': shareholder_distribution,
            'distribution_over_time': distribution_over_time,
            'withdrawals_over_time': withdrawals_over_time,
            'shareholders_list': shareholders_list,
            'withdrawals_list': withdrawals_list,
            'distribution_history': distribution_history,
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def customer_report(request):
    """Get customer report for a vendor (or superuser with user_id)."""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    try:
        user_id = request.GET.get('user_id')
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        if request.user.is_superuser and user_id:
            try:
                vendor = User.objects.get(id=int(user_id))
            except (ValueError, User.DoesNotExist):
                return Response({'error': 'Invalid user_id'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            vendor = request.user
        if not start_date_str or not end_date_str:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=29)
        else:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return Response(
                    {'error': 'Invalid date format. Use YYYY-MM-DD'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        orders_qs = Order.objects.filter(user=vendor)
        date_range = parse_date_range(start_date.isoformat(), end_date.isoformat())
        if date_range:
            start_dt, end_dt = date_range
            orders_qs = orders_qs.filter(created_at__gte=start_dt, created_at__lte=end_dt)
        customer_agg = (
            orders_qs.values('name', 'phone', 'country_code')
            .annotate(
                order_count=Count('id'),
                total_spend=Sum('total'),
                first_order=Min('created_at'),
                last_order=Max('created_at'),
            )
            .order_by('-total_spend')
        )
        unique_customers = customer_agg.count()
        total_customer_spend = sum(Decimal(str(c['total_spend'] or 0)) for c in customer_agg)
        all_orders_dates = list(orders_qs.values_list('created_at__date', flat=True).distinct())
        new_customers = 0
        for fo in orders_qs.values('name', 'phone', 'country_code').annotate(first_in_period=Min('created_at')):
            first_dt = fo['first_in_period']
            if first_dt:
                prev = Order.objects.filter(
                    user=vendor,
                    name=fo['name'],
                    phone=fo['phone'],
                    country_code=fo.get('country_code') or '91',
                    created_at__lt=first_dt
                ).exists()
                if not prev:
                    new_customers += 1
        repeat_customers_agg = [c for c in customer_agg if c['order_count'] >= 2]
        repeat_customers_count = len(repeat_customers_agg)
        avg_orders_per_customer = round(unique_customers and (orders_qs.count() / unique_customers), 1)
        customer_list = []
        for c in customer_agg:
            customer_list.append({
                'name': c['name'] or '—',
                'phone': c['phone'] or '—',
                'country_code': c.get('country_code') or '91',
                'order_count': c['order_count'],
                'total_spend': int(Decimal(str(c['total_spend'] or 0))),
                'first_order_date': c['first_order'].date().isoformat() if c['first_order'] else None,
                'last_order_date': c['last_order'].date().isoformat() if c['last_order'] else None,
            })
        repeat_customers = []
        for c in repeat_customers_agg:
            repeat_customers.append({
                'id': 0,
                'name': c['name'] or '—',
                'phone': c['phone'] or '—',
                'country_code': c.get('country_code') or '91',
                'order_count': c['order_count'],
                'total_spend': int(Decimal(str(c['total_spend'] or 0))),
            })
        new_vs_returning = []
        for single_date in sorted(all_orders_dates):
            day_orders = orders_qs.filter(created_at__date=single_date)
            new_this_day = 0
            for o in day_orders:
                prev = Order.objects.filter(
                    user=vendor,
                    name=o.name,
                    phone=o.phone,
                    country_code=o.country_code or '91',
                    created_at__lt=o.created_at
                ).exists()
                if not prev:
                    new_this_day += 1
            new_vs_returning.append({
                'date': single_date.isoformat() if hasattr(single_date, 'isoformat') else str(single_date)[:10],
                'new': new_this_day,
                'returning': day_orders.count() - new_this_day,
            })
        top_customers_list = [
            {
                'name': c['name'] or '—',
                'phone': c['phone'] or '—',
                'total_spend': int(Decimal(str(c['total_spend'] or 0))),
                'order_count': c['order_count'],
            }
            for c in list(customer_agg[:15])
        ]
        return Response({
            'summary': {
                'total_unique_customers': unique_customers,
                'new_customers': new_customers,
                'repeat_customers': repeat_customers_count,
                'avg_orders_per_customer': avg_orders_per_customer,
                'total_customer_spend': str(total_customer_spend),
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
            },
            'new_vs_returning_over_time': new_vs_returning,
            'top_customers_by_spend': top_customers_list,
            'customer_list': customer_list,
            'repeat_customers': repeat_customers,
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
