from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.core.paginator import Paginator
from ..models import Transaction, TransactionHistory
from ..serializers import TransactionSerializer, TransactionHistorySerializer
from ..utils.date_helpers import parse_date_range


@api_view(['GET'])
def transaction_list(request):
    """Get all transactions for the authenticated user with filtering, search, and pagination"""
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
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        # New filters
        transaction_type = request.GET.get('transaction_type')
        transaction_category = request.GET.get('transaction_category')
        is_system = request.GET.get('is_system')
        
        # Filter by user - superusers can see all transactions and filter by user_id
        # Non-superusers (vendors) should NOT see system transactions (is_system=true)
        if request.user.is_superuser:
            queryset = Transaction.objects.all()
            if user_id:
                try:
                    queryset = queryset.filter(user_id=int(user_id))
                except ValueError:
                    pass
        else:
            # Non-superusers only see their own transactions AND exclude system transactions
            queryset = Transaction.objects.filter(user=request.user, is_system=False)
        
        # Apply filters
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        date_range = parse_date_range(start_date, end_date)
        if date_range:
            start_dt, end_dt = date_range
            queryset = queryset.filter(created_at__gte=start_dt, created_at__lte=end_dt)
        
        # Apply new filters
        if transaction_type:
            queryset = queryset.filter(transaction_type=transaction_type)
        
        if transaction_category:
            queryset = queryset.filter(transaction_category=transaction_category)
        
        # is_system filter only applies to superusers (vendors are already filtered to is_system=False)
        if request.user.is_superuser and is_system is not None and is_system != '':
            if is_system.lower() in ('true', '1', 'yes'):
                queryset = queryset.filter(is_system=True)
            elif is_system.lower() in ('false', '0', 'no'):
                queryset = queryset.filter(is_system=False)
        
        # Apply search
        if search:
            queryset = queryset.filter(
                Q(remarks__icontains=search) | Q(utr__icontains=search) | 
                Q(vpa__icontains=search) | Q(payer_name__icontains=search)
            )
        
        # Select related for performance
        queryset = queryset.select_related('order', 'qr_stand_order').order_by('-created_at')
        
        # Paginate
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages
        
        if page > total_pages and total_pages > 0:
            page = total_pages
        if page < 1:
            page = 1
        
        page_obj = paginator.get_page(page)
        
        serializer = TransactionSerializer(page_obj.object_list, many=True, context={'request': request})
        
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


@api_view(['GET'])
def transaction_detail(request, id):
    """Get a specific transaction"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can access any transaction, regular users only their own (excluding system transactions)
        if request.user.is_superuser:
            transaction = Transaction.objects.select_related('order', 'qr_stand_order').get(id=id)
        else:
            # Non-superusers can only view their own non-system transactions
            transaction = Transaction.objects.select_related('order', 'qr_stand_order').get(
                id=id, user=request.user, is_system=False
            )
        serializer = TransactionSerializer(transaction, context={'request': request})
        return Response({'transaction': serializer.data}, status=status.HTTP_200_OK)
    except Transaction.DoesNotExist:
        return Response(
            {'error': 'Transaction not found'},
            status=status.HTTP_404_NOT_FOUND
        )
