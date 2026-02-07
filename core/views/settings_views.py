from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Sum, Q, Avg
from django.utils import timezone
from datetime import timedelta, date, datetime
from decimal import Decimal
from ..models import Product, Order, Category, Transaction, TransactionHistory, SuperSetting, OrderItem, User, QRStandOrder, ShareholderWithdrawal
from ..serializers import SuperSettingSerializer, UserSerializer, TransactionHistorySerializer, QRStandOrderSerializer, OrderSerializer, ShareholderWithdrawalSerializer
from ..utils.subscription_helpers import get_effective_subscription_end_date, get_subscription_state

# Allowed dashboard date filter values; invalid values fall back to 'today'
DASHBOARD_DATE_FILTER_VALUES = {'today', 'yesterday', 'weekly', 'monthly', 'yearly', 'all'}


def get_dashboard_date_range(date_filter):
    """
    Given date_filter ('today'|'yesterday'|'weekly'|'monthly'|'yearly'|'all')
    and server timezone, return (start_dt, end_dt) as timezone-aware datetimes,
    or (None, None) for 'all'. Invalid date_filter defaults to 'today'.
    """
    if date_filter not in DASHBOARD_DATE_FILTER_VALUES:
        date_filter = 'today'
    if date_filter == 'all':
        return None, None

    now = timezone.now()
    today = now.date()

    if date_filter == 'today':
        start_dt = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        end_dt = start_dt + timedelta(days=1) - timedelta(microseconds=1)
        return start_dt, end_dt

    if date_filter == 'yesterday':
        yesterday = today - timedelta(days=1)
        start_dt = timezone.make_aware(datetime.combine(yesterday, datetime.min.time()))
        end_dt = start_dt + timedelta(days=1) - timedelta(microseconds=1)
        return start_dt, end_dt

    if date_filter == 'weekly':
        # Last 7 days including today
        start_date = today - timedelta(days=6)
        start_dt = timezone.make_aware(datetime.combine(start_date, datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(today, datetime.min.time())) + timedelta(days=1) - timedelta(microseconds=1)
        return start_dt, end_dt

    if date_filter == 'monthly':
        # Current calendar month
        start_dt = timezone.make_aware(datetime.combine(today.replace(day=1), datetime.min.time()))
        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        end_dt = timezone.make_aware(datetime.combine(end_date, datetime.max.time()))
        return start_dt, end_dt

    if date_filter == 'yearly':
        # Current calendar year
        start_dt = timezone.make_aware(datetime.combine(today.replace(month=1, day=1), datetime.min.time()))
        end_dt = timezone.make_aware(datetime.combine(today.replace(month=12, day=31), datetime.max.time()))
        return start_dt, end_dt

    return None, None


@api_view(['GET'])
def dashboard_stats(request):
    """Get enhanced dashboard statistics for the authenticated user"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user_id = request.GET.get('user_id')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # Filter by user - superusers can filter by user_id or show all
        if request.user.is_superuser:
            if user_id:
                try:
                    user_filter = {'user_id': int(user_id)}
                except ValueError:
                    user_filter = {'user': request.user}
            else:
                # Super admin viewing all users - no filter
                user_filter = {}
        else:
            user_filter = {'user': request.user}
        
        # Date range defaults to last 30 days if not provided
        if not start_date:
            start_date = (timezone.now() - timedelta(days=30)).date()
        if not end_date:
            end_date = timezone.now().date()
        
        # Basic counts
        products = Product.objects.filter(**user_filter).count()
        orders = Order.objects.filter(**user_filter).count()
        categories = Category.objects.filter(**user_filter).count()
        transactions = TransactionHistory.objects.filter(**user_filter).count()
        
        # Order statistics
        orders_queryset = Order.objects.filter(**user_filter)
        if start_date:
            orders_queryset = orders_queryset.filter(created_at__date__gte=start_date)
        if end_date:
            orders_queryset = orders_queryset.filter(created_at__date__lte=end_date)
        
        total_revenue = orders_queryset.aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        paid_revenue = orders_queryset.filter(payment_status='paid').aggregate(
            total=Sum('total')
        )['total'] or Decimal('0')
        
        orders_by_status = orders_queryset.values('status').annotate(
            count=Count('id')
        )
        
        # Recent orders (last 10)
        recent_orders = orders_queryset.order_by('-created_at')[:10].values(
            'id', 'name', 'phone', 'table_no', 'status', 'payment_status', 'total', 'created_at'
        )
        
        # Top products by revenue
        top_products = OrderItem.objects.filter(
            order__in=orders_queryset.values_list('id', flat=True)
        ).values(
            'product__name'
        ).annotate(
            total_revenue=Sum('total'),
            total_quantity=Sum('quantity')
        ).order_by('-total_revenue')[:10]
        
        # Revenue by category
        revenue_by_category = OrderItem.objects.filter(
            order__in=orders_queryset.values_list('id', flat=True)
        ).values(
            'product__category__name'
        ).annotate(
            total_revenue=Sum('total')
        ).order_by('-total_revenue')
        
        # Sales trends (daily for last 30 days)
        sales_trends = []
        current_date = start_date
        while current_date <= end_date:
            day_orders = orders_queryset.filter(created_at__date=current_date)
            day_revenue = day_orders.aggregate(total=Sum('total'))['total'] or Decimal('0')
            sales_trends.append({
                'date': current_date.isoformat(),
                'orders': day_orders.count(),
                'revenue': str(day_revenue)
            })
            current_date += timedelta(days=1)
        
        stats = {
            'products': products,
            'orders': orders,
            'categories': categories,
            'transactions': transactions,
            'total_revenue': str(total_revenue),
            'paid_revenue': str(paid_revenue),
            'orders_by_status': list(orders_by_status),
            'recent_orders': list(recent_orders),
            'top_products': list(top_products),
            'revenue_by_category': list(revenue_by_category),
            'sales_trends': sales_trends
        }
        
        return Response({'stats': stats}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_settings(request):
    """Get super settings"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        setting = SuperSetting.objects.first()
        if setting:
            serializer = SuperSettingSerializer(setting, context={'request': request})
            return Response({'setting': serializer.data}, status=status.HTTP_200_OK)
        else:
            return Response({'setting': None}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_public_settings(request):
    """Get public settings (no authentication required) - for menu page to display per_transaction_fee"""
    try:
        setting = SuperSetting.objects.first()
        if setting:
            return Response({
                'setting': {
                    'per_transaction_fee': setting.per_transaction_fee,
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'setting': {
                    'per_transaction_fee': 10,  # Default value
                }
            }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def update_settings(request):
    """Update super settings"""
    # #region agent log
    import json
    import traceback
    with open(r'c:\CODE\My_Cafe\.cursor\debug.log', 'a') as f:
        f.write(json.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'A','location':'settings_views.py:153','message':'Function entry','data':{'method':request.method,'content_type':getattr(request,'content_type',None)},'timestamp':int(timezone.now().timestamp()*1000)})+'\n')
    # #endregion
    
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can update settings'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Use DRF's request.data which automatically handles JSON, form data, etc.
        data = request.data
        # #region agent log
        with open(r'c:\CODE\My_Cafe\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'A','location':'settings_views.py:169','message':'request.data extracted','data':{'data_type':str(type(data)),'data_keys':list(data.keys()) if hasattr(data,'keys') else 'N/A','data_dict':dict(data) if hasattr(data,'__dict__') else str(data)},'timestamp':int(timezone.now().timestamp()*1000)})+'\n')
        # #endregion
        
        # Validate required field: expire_duration_month
        expire_duration_month = data.get('expire_duration_month')
        # #region agent log
        with open(r'c:\CODE\My_Cafe\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'A','location':'settings_views.py:172','message':'expire_duration_month extracted','data':{'value':expire_duration_month,'type':str(type(expire_duration_month))},'timestamp':int(timezone.now().timestamp()*1000)})+'\n')
        # #endregion
        if expire_duration_month is None:
            return Response(
                {'error': 'expire_duration_month is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate expire_duration_month is a positive integer
        try:
            expire_duration_month = int(expire_duration_month)
            # #region agent log
            with open(r'c:\CODE\My_Cafe\.cursor\debug.log', 'a') as f:
                f.write(json.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'D','location':'settings_views.py:181','message':'expire_duration_month converted to int','data':{'value':expire_duration_month},'timestamp':int(timezone.now().timestamp()*1000)})+'\n')
            # #endregion
            if expire_duration_month < 1:
                return Response(
                    {'error': 'expire_duration_month must be a positive integer'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, TypeError):
            return Response(
                {'error': 'expire_duration_month must be a valid integer'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Handle optional fields with defaults
        per_qr_stand_price = data.get('per_qr_stand_price', 0)
        subscription_fee_per_month = data.get('subscription_fee_per_month', 0)
        
        # New transaction system fields
        ug_api = data.get('ug_api')
        per_transaction_fee = data.get('per_transaction_fee', 10)
        is_subscription_fee = data.get('is_subscription_fee', True)
        due_threshold = data.get('due_threshold', 1000)
        is_whatsapp_usage = data.get('is_whatsapp_usage', True)
        whatsapp_per_usage = data.get('whatsapp_per_usage', 0)
        whatsapp_template_marketing = data.get('whatsapp_template_marketing', 'mycafemarketing')
        whatsapp_template_imagemarketing = data.get('whatsapp_template_imagemarketing', 'mycafeimagemarketing')
        share_distribution_day = data.get('share_distribution_day', 7)
        
        # Validate optional fields are non-negative integers
        try:
            per_qr_stand_price = int(per_qr_stand_price) if per_qr_stand_price is not None else 0
            if per_qr_stand_price < 0:
                return Response(
                    {'error': 'per_qr_stand_price must be a non-negative integer'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, TypeError):
            return Response(
                {'error': 'per_qr_stand_price must be a valid integer'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            subscription_fee_per_month = int(subscription_fee_per_month) if subscription_fee_per_month is not None else 0
            if subscription_fee_per_month < 0:
                return Response(
                    {'error': 'subscription_fee_per_month must be a non-negative integer'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, TypeError):
            return Response(
                {'error': 'subscription_fee_per_month must be a valid integer'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate new fields
        try:
            per_transaction_fee = int(per_transaction_fee) if per_transaction_fee is not None else 10
            due_threshold = int(due_threshold) if due_threshold is not None else 1000
            whatsapp_per_usage = int(whatsapp_per_usage) if whatsapp_per_usage is not None else 0
            share_distribution_day = int(share_distribution_day) if share_distribution_day is not None else 7
            
            # Handle boolean fields
            if isinstance(is_subscription_fee, str):
                is_subscription_fee = is_subscription_fee.lower() in ('true', '1', 'yes')
            else:
                is_subscription_fee = bool(is_subscription_fee) if is_subscription_fee is not None else True
                
            if isinstance(is_whatsapp_usage, str):
                is_whatsapp_usage = is_whatsapp_usage.lower() in ('true', '1', 'yes')
            else:
                is_whatsapp_usage = bool(is_whatsapp_usage) if is_whatsapp_usage is not None else True
                
            # Validate share_distribution_day is between 1-28
            if share_distribution_day < 1 or share_distribution_day > 28:
                return Response(
                    {'error': 'share_distribution_day must be between 1 and 28'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, TypeError) as e:
            return Response(
                {'error': f'Invalid field value: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update or create settings
        # Use defaults parameter to provide required fields when creating
        setting, created = SuperSetting.objects.get_or_create(
            id=1,
            defaults={
                'expire_duration_month': expire_duration_month,
                'per_qr_stand_price': per_qr_stand_price,
                'subscription_fee_per_month': subscription_fee_per_month,
                'ug_api': ug_api,
                'per_transaction_fee': per_transaction_fee,
                'is_subscription_fee': is_subscription_fee,
                'due_threshold': due_threshold,
                'is_whatsapp_usage': is_whatsapp_usage,
                'whatsapp_per_usage': whatsapp_per_usage,
                'whatsapp_template_marketing': whatsapp_template_marketing or 'mycafemarketing',
                'whatsapp_template_imagemarketing': whatsapp_template_imagemarketing or 'mycafeimagemarketing',
                'share_distribution_day': share_distribution_day,
            }
        )
        # #region agent log
        with open(r'c:\CODE\My_Cafe\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'B','location':'settings_views.py:244','message':'get_or_create result','data':{'created':created,'existing_expire':getattr(setting,'expire_duration_month',None),'setting_id':setting.id},'timestamp':int(timezone.now().timestamp()*1000)})+'\n')
        # #endregion
        
        # If record already existed, update it with new values
        if not created:
            setting.expire_duration_month = expire_duration_month
            setting.per_qr_stand_price = per_qr_stand_price
            setting.subscription_fee_per_month = subscription_fee_per_month
            setting.ug_api = ug_api
            setting.per_transaction_fee = per_transaction_fee
            setting.is_subscription_fee = is_subscription_fee
            setting.due_threshold = due_threshold
            setting.is_whatsapp_usage = is_whatsapp_usage
            setting.whatsapp_per_usage = whatsapp_per_usage
            setting.whatsapp_template_marketing = whatsapp_template_marketing or 'mycafemarketing'
            setting.whatsapp_template_imagemarketing = whatsapp_template_imagemarketing or 'mycafeimagemarketing'
            setting.share_distribution_day = share_distribution_day
            # Note: balance is NOT updated through this API - only through transactions
        # #region agent log
        with open(r'c:\CODE\My_Cafe\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'C','location':'settings_views.py:256','message':'Values before save','data':{'expire_duration_month':setting.expire_duration_month,'per_qr_stand_price':setting.per_qr_stand_price,'subscription_fee_per_month':setting.subscription_fee_per_month,'created':created},'timestamp':int(timezone.now().timestamp()*1000)})+'\n')
        # #endregion
        
        # Only save if we updated an existing record (new records are already saved by get_or_create)
        if not created:
            setting.save()
        
        serializer = SuperSettingSerializer(setting, context={'request': request})
        return Response({'setting': serializer.data}, status=status.HTTP_200_OK)
        
    except Exception as e:
        # #region agent log
        with open(r'c:\CODE\My_Cafe\.cursor\debug.log', 'a') as f:
            f.write(json.dumps({'sessionId':'debug-session','runId':'run1','hypothesisId':'E','location':'settings_views.py:260','message':'Exception caught','data':{'error':str(e),'error_type':str(type(e).__name__),'traceback':traceback.format_exc()},'timestamp':int(timezone.now().timestamp()*1000)})+'\n')
        # #endregion
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def users_stats(request):
    """Get per-user statistics for super admin"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only superusers can view users statistics'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        users = User.objects.all().order_by('-created_at')
        users_data = []
        
        for user in users:
            # Get statistics for this user
            products_count = Product.objects.filter(user=user).count()
            orders_count = Order.objects.filter(user=user).count()
            categories_count = Category.objects.filter(user=user).count()
            transactions_count = TransactionHistory.objects.filter(user=user).count()
            
            # Calculate revenue
            orders_queryset = Order.objects.filter(user=user)
            total_revenue = orders_queryset.aggregate(
                total=Sum('total')
            )['total'] or Decimal('0')
            
            paid_revenue = orders_queryset.filter(payment_status='paid').aggregate(
                total=Sum('total')
            )['total'] or Decimal('0')
            
            # Serialize user data
            user_serializer = UserSerializer(user, context={'request': request})
            
            users_data.append({
                'user': user_serializer.data,
                'stats': {
                    'products': products_count,
                    'orders': orders_count,
                    'categories': categories_count,
                    'transactions': transactions_count,
                    'total_revenue': str(total_revenue),
                    'paid_revenue': str(paid_revenue),
                }
            })
        
        return Response({'users': users_data}, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def vendor_dashboard_data(request):
    """Get vendor-specific dashboard data including subscription details, transactions, and pending counts"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user = request.user
        today = date.today()
        date_filter = request.GET.get('date_filter', 'today')
        start_dt, end_dt = get_dashboard_date_range(date_filter)

        effective_end = get_effective_subscription_end_date(user)

        # Orders and transactions in the selected date range (or all if date_filter='all')
        orders_base = Order.objects.filter(user=user)
        transactions_base = TransactionHistory.objects.filter(user=user)
        if start_dt is not None:
            orders_in_range = orders_base.filter(created_at__gte=start_dt, created_at__lte=end_dt)
            transactions_in_range = transactions_base.filter(created_at__gte=start_dt, created_at__lte=end_dt)
        else:
            orders_in_range = orders_base
            transactions_in_range = transactions_base

        # Get subscription details
        subscription_type = None
        amount_paid = Decimal('0')
        end_for_type = effective_end or user.subscription_end_date
        if user.subscription_start_date and end_for_type:
            # Calculate subscription type
            months_diff = (end_for_type.year - user.subscription_start_date.year) * 12 + \
                         (end_for_type.month - user.subscription_start_date.month)
            subscription_type = 'yearly' if months_diff >= 12 else 'monthly'
            
            # Calculate total amount paid from subscription transactions
            subscription_transactions = TransactionHistory.objects.filter(
                user=user,
                order__isnull=True
            ).filter(
                Q(remarks__icontains='Subscription') | Q(remarks__icontains='subscription')
            ).filter(status='success')
            
            amount_paid = sum(Decimal(str(t.amount)) for t in subscription_transactions)
        
        # Determine subscription status from effective end date
        subscription_status = get_subscription_state(user, today)
        if subscription_status == 'inactive_with_date':
            subscription_status = 'inactive'
        
        # Get transaction history in date range (for list and breakdown)
        transactions = transactions_in_range.order_by('-created_at')[:50]
        transaction_serializer = TransactionHistorySerializer(transactions, many=True, context={'request': request})

        # Get pending orders count (current state, not filtered by date)
        pending_orders_count = Order.objects.filter(user=user, status='pending').count()

        # Get pending QR stand orders count (current state, not filtered by date)
        pending_qr_orders_count = QRStandOrder.objects.filter(vendor=user, order_status='pending').count()

        # Payment status breakdown for charts (in date range)
        paid_count = transactions_in_range.filter(status='success').count()
        pending_count = transactions_in_range.filter(status='pending').count()
        failed_count = transactions_in_range.filter(status='failed').count()
        payment_status_breakdown = {
            'paid': paid_count,
            'pending': pending_count,
            'failed': failed_count
        }
        
        # Get subscription history (timeline)
        subscription_history = []
        if user.subscription_start_date:
            subscription_transactions = TransactionHistory.objects.filter(
                user=user,
                order__isnull=True
            ).filter(
                Q(remarks__icontains='Subscription') | Q(remarks__icontains='subscription')
            ).order_by('created_at')
            
            subscription_history.append({
                'date': user.subscription_start_date.isoformat(),
                'event': 'subscription_started',
                'subscription_type': subscription_type,
                'amount': str(amount_paid)
            })
            
            for transaction in subscription_transactions:
                subscription_history.append({
                    'date': transaction.created_at.date().isoformat(),
                    'event': 'payment',
                    'amount': str(transaction.amount),
                    'status': transaction.status
                })
        
        # Calculate total orders (in date range)
        total_orders = orders_in_range.count()

        # Calculate total sales (sum of order totals in date range)
        total_sales_result = orders_in_range.aggregate(total=Sum('total'))
        total_sales = total_sales_result['total'] or Decimal('0')

        # Calculate total revenue (successful transactions in date range)
        total_revenue_result = transactions_in_range.filter(status='success').aggregate(total=Sum('amount'))
        total_revenue = total_revenue_result['total'] or Decimal('0')

        # Finance summary: in-range total (legacy keys kept for compatibility)
        range_revenue = transactions_in_range.filter(status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0')
        finance_summary = {
            'today': str(range_revenue),
            'week': str(range_revenue),
            'month': str(range_revenue)
        }
        
        # Best selling products (top 10 by quantity sold, in date range)
        orders_in_range_completed = orders_in_range.filter(status__in=['accepted', 'completed'])
        best_selling_products = OrderItem.objects.filter(
            order__in=orders_in_range_completed
        ).values(
            'product__id',
            'product__name',
            'product__image'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('total')
        ).order_by('-total_quantity')[:10]
        
        best_selling_products_list = []
        for item in best_selling_products:
            best_selling_products_list.append({
                'product_id': item['product__id'],
                'product_name': item['product__name'],
                'product_image': item['product__image'],
                'total_quantity': item['total_quantity'],
                'total_revenue': str(item['total_revenue'] or Decimal('0'))
            })
        
        # Order trends within date range (daily, weekly, monthly series)
        order_trends_daily = []
        order_trends_weekly = []
        order_trends_monthly = []

        if start_dt is not None:
            start_date = start_dt.date()
            end_date = end_dt.date()
            # Daily: one point per day in range
            current = start_date
            while current <= end_date:
                day_start = timezone.make_aware(datetime.combine(current, datetime.min.time()))
                day_end = day_start + timedelta(days=1)
                day_orders = orders_in_range.filter(created_at__gte=day_start, created_at__lt=day_end).count()
                day_revenue = transactions_in_range.filter(status='success', created_at__gte=day_start, created_at__lt=day_end).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                order_trends_daily.append({'date': current.isoformat(), 'orders': day_orders, 'revenue': str(day_revenue)})
                current += timedelta(days=1)
            # Weekly: one point per week (use same days as daily for "weekly" bucket when range <= 7 days)
            if len(order_trends_daily) <= 7:
                order_trends_weekly = list(order_trends_daily)
            else:
                # Aggregate by week (Sunday start)
                week_start = start_date
                while week_start <= end_date:
                    week_end = week_start + timedelta(days=7)
                    ws = timezone.make_aware(datetime.combine(week_start, datetime.min.time()))
                    we = timezone.make_aware(datetime.combine(min(week_end, end_date + timedelta(days=1)), datetime.min.time()))
                    wo = orders_in_range.filter(created_at__gte=ws, created_at__lt=we).count()
                    wr = transactions_in_range.filter(status='success', created_at__gte=ws, created_at__lt=we).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                    order_trends_weekly.append({'date': week_start.isoformat(), 'orders': wo, 'revenue': str(wr)})
                    week_start = week_end
            # Monthly: one point per month in range
            month_date = start_date.replace(day=1)
            while month_date <= end_date:
                month_start_dt = timezone.make_aware(datetime.combine(month_date, datetime.min.time()))
                if month_date.month == 12:
                    next_month = month_date.replace(year=month_date.year + 1, month=1, day=1)
                else:
                    next_month = month_date.replace(month=month_date.month + 1, day=1)
                month_end_dt = timezone.make_aware(datetime.combine(next_month, datetime.min.time())) - timedelta(microseconds=1)
                mo = orders_in_range.filter(created_at__gte=month_start_dt, created_at__lte=month_end_dt).count()
                mr = transactions_in_range.filter(status='success', created_at__gte=month_start_dt, created_at__lte=month_end_dt).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                order_trends_monthly.append({'date': month_date.strftime('%Y-%m'), 'orders': mo, 'revenue': str(mr)})
                month_date = next_month
        else:
            # All time: last 30 days daily, last 12 weeks weekly, last 12 months monthly
            for i in range(30):
                day = today - timedelta(days=29 - i)
                day_start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
                day_end = day_start + timedelta(days=1)
                day_orders = orders_base.filter(created_at__gte=day_start, created_at__lt=day_end).count()
                day_revenue = transactions_base.filter(status='success', created_at__gte=day_start, created_at__lt=day_end).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                order_trends_daily.append({'date': day.isoformat(), 'orders': day_orders, 'revenue': str(day_revenue)})
            for i in range(12):
                week_start = today - timedelta(days=7 * (11 - i))
                week_end = week_start + timedelta(days=7)
                ws = timezone.make_aware(datetime.combine(week_start, datetime.min.time()))
                we = timezone.make_aware(datetime.combine(week_end, datetime.min.time()))
                wo = orders_base.filter(created_at__gte=ws, created_at__lt=we).count()
                wr = transactions_base.filter(status='success', created_at__gte=ws, created_at__lt=we).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                order_trends_weekly.append({'date': week_start.isoformat(), 'orders': wo, 'revenue': str(wr)})
            for i in range(12):
                # Go back (11-i) months from current month
                m = today.month - 1 - (11 - i)
                year = today.year + m // 12
                month = (m % 12) + 1
                month_date = date(year, month, 1)
                month_start_dt = timezone.make_aware(datetime.combine(month_date, datetime.min.time()))
                if month == 12:
                    month_end_dt = timezone.make_aware(datetime.combine(date(year + 1, 1, 1), datetime.min.time())) - timedelta(microseconds=1)
                else:
                    month_end_dt = timezone.make_aware(datetime.combine(date(year, month + 1, 1), datetime.min.time())) - timedelta(microseconds=1)
                mo = orders_base.filter(created_at__gte=month_start_dt, created_at__lte=month_end_dt).count()
                mr = transactions_base.filter(status='success', created_at__gte=month_start_dt, created_at__lte=month_end_dt).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                order_trends_monthly.append({'date': month_date.strftime('%Y-%m'), 'orders': mo, 'revenue': str(mr)})

        order_trends = {
            'daily': order_trends_daily,
            'weekly': order_trends_weekly,
            'monthly': order_trends_monthly
        }
        
        # Recent orders (last 20, in date range)
        recent_orders = orders_in_range.order_by('-created_at')[:20]
        recent_orders_serializer = OrderSerializer(recent_orders, many=True, context={'request': request})

        # Pending orders (list for dashboard sections)
        pending_orders_qs = Order.objects.filter(user=user, status='pending').order_by('-created_at')[:20]
        pending_orders_serializer = OrderSerializer(pending_orders_qs, many=True, context={'request': request})

        # Pending QR stand orders (list for dashboard sections)
        pending_qr_orders_qs = QRStandOrder.objects.filter(vendor=user, order_status='pending').order_by('-created_at')[:20]
        pending_qr_orders_serializer = QRStandOrderSerializer(pending_qr_orders_qs, many=True, context={'request': request})

        # Total products and total QR stand orders
        total_products = Product.objects.filter(user=user).count()
        total_qr_stand_orders = QRStandOrder.objects.filter(vendor=user).count()

        # Top revenue products (top 10 by total revenue, in date range)
        top_revenue_products_qs = OrderItem.objects.filter(
            order__in=orders_in_range_completed
        ).values(
            'product__id',
            'product__name',
            'product__image'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('total')
        ).order_by('-total_revenue')[:10]
        top_revenue_products_list = []
        for item in top_revenue_products_qs:
            top_revenue_products_list.append({
                'product_id': item['product__id'],
                'product_name': item['product__name'],
                'product_image': item['product__image'],
                'total_quantity': item['total_quantity'],
                'total_revenue': str(item['total_revenue'] or Decimal('0'))
            })

        # Repeat customers (order_count >= 2 in date range)
        customer_agg = (
            orders_in_range.values('name', 'phone', 'country_code')
            .annotate(
                order_count=Count('id'),
                total_spend=Sum('total'),
            )
            .order_by('-total_spend')
        )
        repeat_customers_agg = [c for c in customer_agg if c['order_count'] >= 2]
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
        
        return Response({
            'subscription': {
                'type': subscription_type,
                'start_date': user.subscription_start_date.isoformat() if user.subscription_start_date else None,
                'end_date': effective_end.isoformat() if effective_end else None,
                'amount_paid': str(amount_paid),
                'status': subscription_status
            },
            'transactions': transaction_serializer.data,
            'pending_orders_count': pending_orders_count,
            'pending_qr_orders_count': pending_qr_orders_count,
            'pending_orders': pending_orders_serializer.data,
            'pending_qr_orders': pending_qr_orders_serializer.data,
            'payment_status_breakdown': payment_status_breakdown,
            'subscription_history': subscription_history,
            'total_orders': total_orders,
            'total_sales': str(total_sales),
            'total_revenue': str(total_revenue),
            'total_products': total_products,
            'total_qr_stand_orders': total_qr_stand_orders,
            'finance_summary': finance_summary,
            'best_selling_products': best_selling_products_list,
            'top_revenue_products': top_revenue_products_list,
            'order_trends': order_trends,
            'recent_orders': recent_orders_serializer.data,
            'repeat_customers': repeat_customers,
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def super_admin_dashboard_data(request):
    """Get super admin dashboard data with system-wide analytics"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can access this endpoint'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        today = date.today()
        date_filter = request.GET.get('date_filter', 'today')
        start_dt, end_dt = get_dashboard_date_range(date_filter)

        if start_dt is not None:
            transactions_in_range = TransactionHistory.objects.filter(
                created_at__gte=start_dt, created_at__lte=end_dt
            )
        else:
            transactions_in_range = TransactionHistory.objects.all()

        # User statistics (current state, not filtered by date)
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        deactivated_users = User.objects.filter(is_active=False).count()

        # Total revenue (system-wide, in date range)
        total_revenue = transactions_in_range.filter(status='success').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')

        # Revenue trends: days in range, or last 30 days for "all"
        revenue_trends = []
        if start_dt is not None:
            start_date = start_dt.date()
            end_date = end_dt.date()
            current = start_date
            while current <= end_date:
                day_revenue = transactions_in_range.filter(
                    status='success',
                    created_at__date=current
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                revenue_trends.append({'date': current.isoformat(), 'revenue': str(day_revenue)})
                current += timedelta(days=1)
        else:
            for i in range(30):
                day = today - timedelta(days=29 - i)
                day_revenue = transactions_in_range.filter(
                    status='success',
                    created_at__date=day
                ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                revenue_trends.append({'date': day.isoformat(), 'revenue': str(day_revenue)})

        # Recent transactions (last 50, in date range)
        recent_transactions = transactions_in_range.order_by('-created_at')[:50]
        transaction_serializer = TransactionHistorySerializer(recent_transactions, many=True, context={'request': request})

        # Pending QR stand orders (current state, not filtered by date)
        pending_qr_orders = QRStandOrder.objects.filter(order_status='pending').order_by('-created_at')[:20]
        qr_order_serializer = QRStandOrderSerializer(pending_qr_orders, many=True, context={'request': request})

        # Pending KYC requests count (current state)
        pending_kyc_count = User.objects.filter(kyc_status=User.KYC_PENDING).count()

        # Total transactions count (in date range)
        total_transactions = transactions_in_range.count()

        # QR earnings (in date range)
        qr_earnings = transactions_in_range.filter(
            status='success',
            order__isnull=False
        ).filter(
            Q(remarks__icontains='QR') | Q(remarks__icontains='qr')
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # Subscription earnings (in date range)
        subscription_earnings = transactions_in_range.filter(
            status='success',
            order__isnull=True
        ).filter(
            Q(remarks__icontains='Subscription') | Q(remarks__icontains='subscription')
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # Pending QR stand orders count (current state)
        pending_qr_orders_count = QRStandOrder.objects.filter(order_status='pending').count()

        # Transactions trend (days in range or last 30 for "all")
        transactions_trend = []
        if start_dt is not None:
            start_date = start_dt.date()
            end_date = end_dt.date()
            current = start_date
            while current <= end_date:
                cnt = transactions_in_range.filter(created_at__date=current).count()
                transactions_trend.append({'date': current.isoformat(), 'count': cnt})
                current += timedelta(days=1)
        else:
            for i in range(30):
                day = today - timedelta(days=29 - i)
                cnt = transactions_in_range.filter(created_at__date=day).count()
                transactions_trend.append({'date': day.isoformat(), 'count': cnt})

        # Users overview (orders/revenue in date range)
        users_overview = []
        all_users = User.objects.all()[:50]
        for user_obj in all_users:
            if start_dt is not None:
                user_orders = Order.objects.filter(user=user_obj, created_at__gte=start_dt, created_at__lte=end_dt).count()
                user_revenue = transactions_in_range.filter(user=user_obj, status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0')
            else:
                user_orders = Order.objects.filter(user=user_obj).count()
                user_revenue = TransactionHistory.objects.filter(user=user_obj, status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0')
            users_overview.append({
                'id': user_obj.id,
                'name': user_obj.name,
                'phone': user_obj.phone,
                'is_active': user_obj.is_active,
                'is_superuser': user_obj.is_superuser,
                'total_orders': user_orders,
                'total_revenue': str(user_revenue),
                'kyc_status': user_obj.kyc_status,
            })

        # System balance (from SuperSetting)
        setting = SuperSetting.objects.filter(id=1).first()
        system_balance = int(getattr(setting, 'balance', 0) or 0)

        # Transaction and WhatsApp earnings (in date range)
        transaction_earnings = transactions_in_range.filter(
            status='success',
            transaction_category='transaction_fee'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        whatsapp_earnings = transactions_in_range.filter(
            status='success',
            transaction_category='whatsapp_usage'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        # Vendor-only stats (exclude superusers)
        vendors_qs = User.objects.filter(is_superuser=False)
        total_vendors = vendors_qs.count()
        active_vendors = vendors_qs.filter(is_active=True).count()
        inactive_vendors = vendors_qs.filter(is_active=False).count()
        # Effective end date = expire_date or subscription_end_date
        expired_vendors = vendors_qs.filter(
            Q(expire_date__lt=today, expire_date__isnull=False) |
            Q(expire_date__isnull=True, subscription_end_date__lt=today, subscription_end_date__isnull=False)
        ).count()
        due_threshold = getattr(setting, 'due_threshold', 1000) if setting else 1000
        due_blocked_vendors = vendors_qs.filter(due_balance__gte=due_threshold).count()
        total_due_amount = vendors_qs.aggregate(total=Sum('due_balance'))['total'] or 0

        # Pending KYC requests (list for table)
        pending_kyc_users = User.objects.filter(kyc_status=User.KYC_PENDING).order_by('-created_at')[:50]
        pending_kyc_serializer = UserSerializer(pending_kyc_users, many=True, context={'request': request})

        # Pending withdrawals (list for table)
        pending_withdrawals_qs = ShareholderWithdrawal.objects.filter(status='pending').select_related('user').order_by('-created_at')[:20]
        pending_withdrawals_serializer = ShareholderWithdrawalSerializer(pending_withdrawals_qs, many=True, context={'request': request})

        # Top revenue vendors (for chart, in date range)
        top_revenue_vendors = []
        vendors_for_revenue = User.objects.filter(is_superuser=False).order_by('id')[:100]
        for v in vendors_for_revenue:
            rev = transactions_in_range.filter(user=v, status='success').aggregate(total=Sum('amount'))['total'] or Decimal('0')
            if start_dt is not None:
                orders_count = Order.objects.filter(user=v, created_at__gte=start_dt, created_at__lte=end_dt).count()
            else:
                orders_count = Order.objects.filter(user=v).count()
            logo_url = None
            if v.logo:
                logo_url = request.build_absolute_uri(v.logo.url)
            top_revenue_vendors.append({
                'id': v.id,
                'name': v.name or '',
                'phone': v.phone or '',
                'logo_url': logo_url,
                'total_revenue': float(rev),
                'total_orders': orders_count,
            })
        top_revenue_vendors.sort(key=lambda x: x['total_revenue'], reverse=True)
        top_revenue_vendors = top_revenue_vendors[:20]

        # Financial trends (daily in range or last 30 for "all")
        financial_trends = []
        if start_dt is not None:
            start_date = start_dt.date()
            end_date = end_dt.date()
            current = start_date
            while current <= end_date:
                day_income = transactions_in_range.filter(status='success', created_at__date=current).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                day_outgoing = ShareholderWithdrawal.objects.filter(status='approved', updated_at__date=current).aggregate(total=Sum('amount'))['total'] or 0
                day_outgoing = Decimal(str(day_outgoing))
                profit = day_income - day_outgoing
                financial_trends.append({
                    'date': current.isoformat(),
                    'income': float(day_income),
                    'outgoing': float(day_outgoing),
                    'profit': float(profit) if profit >= 0 else 0,
                    'loss': float(-profit) if profit < 0 else 0,
                })
                current += timedelta(days=1)
        else:
            for i in range(30):
                day = today - timedelta(days=29 - i)
                day_income = transactions_in_range.filter(status='success', created_at__date=day).aggregate(total=Sum('amount'))['total'] or Decimal('0')
                day_outgoing = ShareholderWithdrawal.objects.filter(status='approved', updated_at__date=day).aggregate(total=Sum('amount'))['total'] or 0
                day_outgoing = Decimal(str(day_outgoing))
                profit = day_income - day_outgoing
                financial_trends.append({
                    'date': day.isoformat(),
                    'income': float(day_income),
                    'outgoing': float(day_outgoing),
                    'profit': float(profit) if profit >= 0 else 0,
                    'loss': float(-profit) if profit < 0 else 0,
                })

        # Revenue breakdown (for pie chart)
        revenue_breakdown = {
            'qr_stand_earnings': float(qr_earnings),
            'due_collection': 0,
            'subscription_earnings': float(subscription_earnings),
            'transaction_earnings': float(transaction_earnings),
            'whatsapp_earnings': float(whatsapp_earnings),
            'total': float(total_revenue),
        }
        
        return Response({
            'users': {
                'total': total_users,
                'active': active_users,
                'deactivated': deactivated_users
            },
            'revenue': {
                'total': str(total_revenue),
                'trends': revenue_trends
            },
            'pending_qr_orders': qr_order_serializer.data,
            'pending_kyc_count': pending_kyc_count,
            'transactions': transaction_serializer.data,
            'total_transactions': total_transactions,
            'qr_earnings': str(qr_earnings),
            'subscription_earnings': str(subscription_earnings),
            'pending_qr_orders_count': pending_qr_orders_count,
            'transactions_trend': transactions_trend,
            'users_overview': users_overview,
            'system_balance': system_balance,
            'transaction_earnings': str(transaction_earnings),
            'whatsapp_earnings': str(whatsapp_earnings),
            'total_vendors': total_vendors,
            'active_vendors': active_vendors,
            'inactive_vendors': inactive_vendors,
            'expired_vendors': expired_vendors,
            'due_blocked_vendors': due_blocked_vendors,
            'total_due_amount': total_due_amount,
            'pending_kyc_requests': pending_kyc_serializer.data,
            'pending_withdrawals': pending_withdrawals_serializer.data,
            'top_revenue_vendors': top_revenue_vendors,
            'financial_trends': financial_trends,
            'revenue_breakdown': revenue_breakdown,
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
