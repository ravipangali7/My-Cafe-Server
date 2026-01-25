from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Sum, Q, Avg
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from ..models import Product, Order, Category, TransactionHistory, SuperSetting, OrderItem, User
from ..serializers import SuperSettingSerializer, UserSerializer


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


@api_view(['POST'])
def update_settings(request):
    """Update super settings"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        from rest_framework import status
        import json
        
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        expire_duration_month = data.get('expire_duration_month')
        
        if expire_duration_month is None:
            return Response(
                {'error': 'expire_duration_month is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        setting, created = SuperSetting.objects.get_or_create(id=1)
        setting.expire_duration_month = int(expire_duration_month)
        setting.save()
        
        serializer = SuperSettingSerializer(setting, context={'request': request})
        return Response({'setting': serializer.data}, status=status.HTTP_200_OK)
        
    except Exception as e:
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
