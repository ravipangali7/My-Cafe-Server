from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Sum, Q, Avg
from django.utils import timezone
from datetime import timedelta, date, datetime
from decimal import Decimal
from ..models import Product, Order, Category, Transaction, TransactionHistory, SuperSetting, OrderItem, User, QRStandOrder
from ..serializers import SuperSettingSerializer, UserSerializer, TransactionHistorySerializer, QRStandOrderSerializer, OrderSerializer


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
        ug_client_transaction_id = data.get('ug_client_transaction_id')
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
                'ug_client_transaction_id': ug_client_transaction_id,
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
            setting.ug_client_transaction_id = ug_client_transaction_id
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
        
        # Get subscription details
        subscription_type = None
        amount_paid = Decimal('0')
        
        if user.subscription_start_date and user.subscription_end_date:
            # Calculate subscription type
            months_diff = (user.subscription_end_date.year - user.subscription_start_date.year) * 12 + \
                         (user.subscription_end_date.month - user.subscription_start_date.month)
            subscription_type = 'yearly' if months_diff >= 12 else 'monthly'
            
            # Calculate total amount paid from subscription transactions
            subscription_transactions = TransactionHistory.objects.filter(
                user=user,
                order__isnull=True
            ).filter(
                Q(remarks__icontains='Subscription') | Q(remarks__icontains='subscription')
            ).filter(status='success')
            
            amount_paid = sum(Decimal(str(t.amount)) for t in subscription_transactions)
        
        # Determine subscription status
        subscription_status = 'inactive'
        if user.subscription_end_date:
            if user.subscription_end_date >= today and user.is_active:
                subscription_status = 'active'
            elif user.subscription_end_date < today:
                subscription_status = 'expired'
            else:
                subscription_status = 'inactive'
        else:
            subscription_status = 'no_subscription'
        
        # Get transaction history (all transactions for the user)
        transactions = TransactionHistory.objects.filter(user=user).order_by('-created_at')[:50]
        transaction_serializer = TransactionHistorySerializer(transactions, many=True, context={'request': request})
        
        # Get pending orders count
        pending_orders_count = Order.objects.filter(user=user, status='pending').count()
        
        # Get pending QR stand orders count
        pending_qr_orders_count = QRStandOrder.objects.filter(vendor=user, order_status='pending').count()
        
        # Payment status breakdown for charts
        all_transactions = TransactionHistory.objects.filter(user=user)
        paid_count = all_transactions.filter(status='success').count()
        pending_count = all_transactions.filter(status='pending').count()
        failed_count = all_transactions.filter(status='failed').count()
        
        total_transactions = all_transactions.count()
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
        
        # Calculate total orders
        total_orders = Order.objects.filter(user=user).count()
        
        # Calculate total sales (sum of all order totals)
        total_sales_result = Order.objects.filter(user=user).aggregate(total=Sum('total'))
        total_sales = total_sales_result['total'] or Decimal('0')
        
        # Calculate total revenue (sum of successful transactions)
        total_revenue_result = TransactionHistory.objects.filter(
            user=user,
            status='success'
        ).aggregate(total=Sum('amount'))
        total_revenue = total_revenue_result['total'] or Decimal('0')
        
        # Finance summary (today/week/month)
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)
        
        today_revenue = TransactionHistory.objects.filter(
            user=user,
            status='success',
            created_at__gte=today_start
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        week_revenue = TransactionHistory.objects.filter(
            user=user,
            status='success',
            created_at__gte=week_start
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        month_revenue = TransactionHistory.objects.filter(
            user=user,
            status='success',
            created_at__gte=month_start
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        finance_summary = {
            'today': str(today_revenue),
            'week': str(week_revenue),
            'month': str(month_revenue)
        }
        
        # Best selling products (top 10 by quantity sold)
        best_selling_products = OrderItem.objects.filter(
            order__user=user,
            order__status__in=['accepted', 'completed']
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
        
        # Order trends (daily for last 30 days, monthly for last 12 months)
        order_trends_daily = []
        for i in range(30):
            day = today - timedelta(days=29-i)
            day_start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
            day_end = day_start + timedelta(days=1)
            
            day_orders = Order.objects.filter(
                user=user,
                created_at__gte=day_start,
                created_at__lt=day_end
            ).count()
            
            day_revenue = TransactionHistory.objects.filter(
                user=user,
                status='success',
                created_at__gte=day_start,
                created_at__lt=day_end
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            order_trends_daily.append({
                'date': day.isoformat(),
                'orders': day_orders,
                'revenue': str(day_revenue)
            })
        
        order_trends_monthly = []
        for i in range(12):
            month_date = today.replace(day=1) - timedelta(days=30 * (11-i))
            month_start_dt = timezone.make_aware(datetime.combine(month_date.replace(day=1), datetime.min.time()))
            if month_date.month == 12:
                month_end_dt = timezone.make_aware(datetime.combine(month_date.replace(year=month_date.year+1, month=1, day=1), datetime.min.time()))
            else:
                month_end_dt = timezone.make_aware(datetime.combine(month_date.replace(month=month_date.month+1, day=1), datetime.min.time()))
            
            month_orders = Order.objects.filter(
                user=user,
                created_at__gte=month_start_dt,
                created_at__lt=month_end_dt
            ).count()
            
            month_revenue = TransactionHistory.objects.filter(
                user=user,
                status='success',
                created_at__gte=month_start_dt,
                created_at__lt=month_end_dt
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            order_trends_monthly.append({
                'date': month_date.strftime('%Y-%m'),
                'orders': month_orders,
                'revenue': str(month_revenue)
            })
        
        order_trends = {
            'daily': order_trends_daily,
            'monthly': order_trends_monthly
        }
        
        # Recent orders (last 20)
        recent_orders = Order.objects.filter(user=user).order_by('-created_at')[:20]
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

        # Top revenue products (top 10 by total revenue)
        top_revenue_products_qs = OrderItem.objects.filter(
            order__user=user,
            order__status__in=['accepted', 'completed']
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

        # Repeat customers (order_count >= 2, all time for vendor)
        orders_qs = Order.objects.filter(user=user)
        customer_agg = (
            orders_qs.values('name', 'phone', 'country_code')
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
                'end_date': user.subscription_end_date.isoformat() if user.subscription_end_date else None,
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
        # User statistics
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        deactivated_users = User.objects.filter(is_active=False).count()
        
        # Total revenue (system-wide)
        total_revenue = TransactionHistory.objects.filter(status='success').aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        # Revenue trends (last 30 days)
        revenue_trends = []
        today = date.today()
        for i in range(30):
            day = today - timedelta(days=29-i)
            day_revenue = TransactionHistory.objects.filter(
                status='success',
                created_at__date=day
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            revenue_trends.append({
                'date': day.isoformat(),
                'revenue': str(day_revenue)
            })
        
        # Recent transactions (last 50)
        recent_transactions = TransactionHistory.objects.all().order_by('-created_at')[:50]
        transaction_serializer = TransactionHistorySerializer(recent_transactions, many=True, context={'request': request})
        
        # Pending QR stand orders
        pending_qr_orders = QRStandOrder.objects.filter(order_status='pending').order_by('-created_at')[:20]
        qr_order_serializer = QRStandOrderSerializer(pending_qr_orders, many=True, context={'request': request})
        
        # Pending KYC requests count
        pending_kyc_count = User.objects.filter(kyc_status=User.KYC_PENDING).count()
        
        # Total transactions count
        total_transactions = TransactionHistory.objects.count()
        
        # QR earnings (from QR stand order transactions)
        qr_earnings = TransactionHistory.objects.filter(
            status='success',
            order__isnull=False
        ).filter(
            Q(remarks__icontains='QR') | Q(remarks__icontains='qr')
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # Subscription earnings (from subscription transactions)
        subscription_earnings = TransactionHistory.objects.filter(
            status='success',
            order__isnull=True
        ).filter(
            Q(remarks__icontains='Subscription') | Q(remarks__icontains='subscription')
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # Pending QR stand orders count
        pending_qr_orders_count = QRStandOrder.objects.filter(order_status='pending').count()
        
        # Transactions trend (last 30 days)
        transactions_trend = []
        for i in range(30):
            day = today - timedelta(days=29-i)
            day_transactions = TransactionHistory.objects.filter(
                created_at__date=day
            ).count()
            
            transactions_trend.append({
                'date': day.isoformat(),
                'count': day_transactions
            })
        
        # Users overview (list of users with key stats)
        users_overview = []
        all_users = User.objects.all()[:50]  # Limit to 50 for performance
        for user_obj in all_users:
            user_orders = Order.objects.filter(user=user_obj).count()
            user_revenue = TransactionHistory.objects.filter(
                user=user_obj,
                status='success'
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
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
            'users_overview': users_overview
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
