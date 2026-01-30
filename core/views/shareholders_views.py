from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q, Sum
from django.core.paginator import Paginator
import json
import logging
from ..models import User, Transaction
from ..serializers import ShareholderSerializer, TransactionSerializer

logger = logging.getLogger(__name__)


@api_view(['GET'])
def shareholders_list(request):
    """List all shareholders (users with is_shareholder=True)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can view shareholders'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Get query parameters
        search = request.GET.get('search', '').strip()
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))
        
        # Get shareholders
        queryset = User.objects.filter(is_shareholder=True)
        
        # Apply search
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(phone__icontains=search)
            )
        
        # Order by share_percentage (highest first)
        queryset = queryset.order_by('-share_percentage', '-balance')
        
        # Paginate
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages
        
        if page > total_pages and total_pages > 0:
            page = total_pages
        if page < 1:
            page = 1
        
        page_obj = paginator.get_page(page)
        
        serializer = ShareholderSerializer(page_obj, many=True, context={'request': request})
        
        # Calculate totals
        total_percentage = queryset.aggregate(total=Sum('share_percentage'))['total'] or 0
        total_balance = queryset.aggregate(total=Sum('balance'))['total'] or 0
        
        return Response({
            'shareholders': serializer.data,
            'count': paginator.count,
            'page': page,
            'total_pages': total_pages,
            'page_size': page_size,
            'total_percentage': total_percentage,
            'total_balance': total_balance
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f'Error listing shareholders: {str(e)}')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def shareholder_detail(request, id):
    """Get shareholder details including transaction history"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can view shareholder details'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        user = User.objects.get(id=id)
        
        if not user.is_shareholder:
            return Response(
                {'error': 'User is not a shareholder'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = ShareholderSerializer(user, context={'request': request})
        
        # Get recent transactions for this shareholder
        transactions = Transaction.objects.filter(
            user=user,
            transaction_category__in=['share_distribution', 'share_withdrawal']
        ).order_by('-created_at')[:20]
        
        txn_serializer = TransactionSerializer(transactions, many=True, context={'request': request})
        
        return Response({
            'shareholder': serializer.data,
            'transactions': txn_serializer.data
        }, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response(
            {'error': 'User not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f'Error getting shareholder details: {str(e)}')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def shareholder_update(request, id):
    """Update shareholder status and share percentage"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can update shareholders'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        user = User.objects.get(id=id)
        
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        # Update is_shareholder if provided
        if 'is_shareholder' in data:
            is_shareholder = data.get('is_shareholder')
            if isinstance(is_shareholder, str):
                is_shareholder = is_shareholder.lower() in ('true', '1', 'yes')
            user.is_shareholder = bool(is_shareholder)
        
        # Update share_percentage if provided
        if 'share_percentage' in data:
            share_percentage = int(data.get('share_percentage', 0))
            if share_percentage < 0 or share_percentage > 100:
                return Response(
                    {'error': 'share_percentage must be between 0 and 100'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.share_percentage = share_percentage
        
        # Update address if provided
        if 'address' in data:
            user.address = data.get('address', '')
        
        user.save()
        
        # Validate total percentage doesn't exceed 100%
        total_percentage = User.objects.filter(is_shareholder=True).aggregate(
            total=Sum('share_percentage')
        )['total'] or 0
        
        if total_percentage > 100:
            logger.warning(f'Total shareholder percentage ({total_percentage}%) exceeds 100%')
        
        serializer = ShareholderSerializer(user, context={'request': request})
        
        return Response({
            'message': 'Shareholder updated successfully',
            'shareholder': serializer.data,
            'total_percentage': total_percentage,
            'warning': 'Total shareholder percentage exceeds 100%' if total_percentage > 100 else None
        }, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response(
            {'error': 'User not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except ValueError as e:
        return Response(
            {'error': f'Invalid value: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        logger.error(f'Error updating shareholder: {str(e)}')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
