from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, Sum
from django.core.paginator import Paginator
import json
import logging
from ..models import User, SuperSetting
from ..serializers import VendorDueSerializer
# NOTE: process_due_payment is now called in payment_views.py on payment success

logger = logging.getLogger(__name__)


@api_view(['GET'])
def due_status(request):
    """Get current user's due status for threshold check"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Get settings for threshold
        settings = SuperSetting.objects.first()
        due_threshold = settings.due_threshold if settings else 1000
        
        # Get user's due balance
        due_balance = request.user.due_balance
        
        # Determine if user is blocked (due exceeds threshold)
        is_blocked = due_balance > due_threshold
        
        return Response({
            'due_balance': due_balance,
            'due_threshold': due_threshold,
            'is_blocked': is_blocked
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f'Error getting due status: {str(e)}')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def dues_list(request):
    """List all vendors with outstanding dues"""
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
        over_threshold_only = request.GET.get('over_threshold', '').lower() == 'true'
        
        # Get settings for threshold
        settings = SuperSetting.objects.first()
        due_threshold = settings.due_threshold if settings else 1000
        
        # Superusers see all vendors, regular users see only their own
        if request.user.is_superuser:
            # Get all vendors with dues > 0
            queryset = User.objects.filter(due_balance__gt=0, is_superuser=False)
        else:
            # Regular users can only see their own dues
            if request.user.due_balance > 0:
                queryset = User.objects.filter(id=request.user.id)
            else:
                return Response({
                    'vendors': [],
                    'count': 0,
                    'page': 1,
                    'total_pages': 0,
                    'page_size': page_size,
                    'total_dues': 0,
                    'due_threshold': due_threshold
                }, status=status.HTTP_200_OK)
        
        # Filter by over threshold
        if over_threshold_only:
            queryset = queryset.filter(due_balance__gt=due_threshold)
        
        # Apply search
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(phone__icontains=search)
            )
        
        # Order by due_balance (highest first)
        queryset = queryset.order_by('-due_balance')
        
        # Paginate
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages
        
        if page > total_pages and total_pages > 0:
            page = total_pages
        if page < 1:
            page = 1
        
        page_obj = paginator.get_page(page)
        
        serializer = VendorDueSerializer(
            page_obj, 
            many=True, 
            context={'request': request, 'due_threshold': due_threshold}
        )
        
        # Calculate total dues
        total_dues = queryset.aggregate(total=Sum('due_balance'))['total'] or 0
        over_threshold_count = queryset.filter(due_balance__gt=due_threshold).count()
        
        return Response({
            'vendors': serializer.data,
            'count': paginator.count,
            'page': page,
            'total_pages': total_pages,
            'page_size': page_size,
            'total_dues': total_dues,
            'due_threshold': due_threshold,
            'over_threshold_count': over_threshold_count
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f'Error listing dues: {str(e)}')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def due_detail(request, id):
    """Get vendor due details"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user = User.objects.get(id=id)
        
        # Check permissions
        if not request.user.is_superuser and user != request.user:
            return Response(
                {'error': 'You do not have permission to view this vendor'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        settings = SuperSetting.objects.first()
        due_threshold = settings.due_threshold if settings else 1000
        
        serializer = VendorDueSerializer(
            user, 
            context={'request': request, 'due_threshold': due_threshold}
        )
        
        return Response({
            'vendor': serializer.data,
            'due_threshold': due_threshold
        }, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response(
            {'error': 'Vendor not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f'Error getting due details: {str(e)}')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def due_pay(request):
    """
    DISABLED: Direct due payment is no longer allowed.
    Due payments must be made through UG payment flow.
    
    Use the following flow instead:
    1. POST /api/payment/initiate/ with payment_type='dues'
    2. Complete payment on UG gateway
    3. Due balance will be updated automatically on payment success
    """
    return Response(
        {
            'error': 'Direct due payment is disabled. Please use UG payment flow.',
            'message': 'Use POST /api/payment/initiate/ with payment_type="dues" to pay dues.',
            'payment_flow': {
                'step1': 'POST /api/payment/initiate/ with payment_type="dues", reference_id (vendor_id), amount, customer_name, customer_mobile',
                'step2': 'Redirect user to payment_url received in response',
                'step3': 'Due balance updates automatically on successful payment'
            }
        },
        status=status.HTTP_400_BAD_REQUEST
    )
