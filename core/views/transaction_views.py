from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.core.paginator import Paginator
from ..models import TransactionHistory
from ..serializers import TransactionHistorySerializer


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
        
        # Apply filters
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Apply search
        if search:
            queryset = queryset.filter(
                Q(remarks__icontains=search) | Q(utr__icontains=search) | 
                Q(vpa__icontains=search) | Q(payer_name__icontains=search)
            )
        
        # Select related for performance
        queryset = queryset.select_related('order').order_by('-created_at')
        
        # Paginate
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages
        
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1
        
        page_obj = paginator.get_page(page)
        
        serializer = TransactionHistorySerializer(page_obj.object_list, many=True, context={'request': request})
        
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
        # Superusers can access any transaction, regular users only their own
        if request.user.is_superuser:
            transaction = TransactionHistory.objects.select_related('order').get(id=id)
        else:
            transaction = TransactionHistory.objects.select_related('order').get(id=id, user=request.user)
        serializer = TransactionHistorySerializer(transaction, context={'request': request})
        return Response({'transaction': serializer.data}, status=status.HTTP_200_OK)
    except TransactionHistory.DoesNotExist:
        return Response(
            {'error': 'Transaction not found'},
            status=status.HTTP_404_NOT_FOUND
        )
