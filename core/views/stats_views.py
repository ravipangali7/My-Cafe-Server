from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Count, Sum, Q
from ..models import Product, Order, Category, TransactionHistory, Unit, User
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
        
        return Response({
            'total': total,
            'active': active,
            'inactive': inactive,
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
        
        # Orders by status
        by_status = queryset.values('status').annotate(
            count=Count('id')
        )
        
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
        
        # Apply date filters
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        total = queryset.count()
        
        # Transactions by status
        by_status = queryset.values('status').annotate(
            count=Count('id'),
            total_amount=Sum('amount')
        )
        
        # Total revenue
        revenue = queryset.filter(status='success').aggregate(
            total_revenue=Sum('amount')
        )['total_revenue'] or Decimal('0')
        
        return Response({
            'total': total,
            'revenue': str(revenue),
            'by_status': list(by_status)
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
        queryset = User.objects.all()
        
        total = queryset.count()
        active = queryset.filter(is_active=True).count()
        inactive = queryset.filter(is_active=False).count()
        superusers = queryset.filter(is_superuser=True).count()
        
        return Response({
            'total': total,
            'active': active,
            'inactive': inactive,
            'superusers': superusers
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
