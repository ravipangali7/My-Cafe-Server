from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from django.core.paginator import Paginator
import json
import logging
from ..models import User, ShareholderWithdrawal
from ..serializers import ShareholderWithdrawalSerializer
from ..utils.transaction_helpers import process_shareholder_withdrawal

logger = logging.getLogger(__name__)


@api_view(['GET'])
def withdrawals_list(request):
    """List all withdrawal requests"""
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
        status_filter = request.GET.get('status')
        
        # Superusers see all, shareholders see only their own
        if request.user.is_superuser:
            queryset = ShareholderWithdrawal.objects.all()
        else:
            # Regular shareholders can only see their own withdrawals
            if not request.user.is_shareholder:
                return Response(
                    {'error': 'Only shareholders can view withdrawals'},
                    status=status.HTTP_403_FORBIDDEN
                )
            queryset = ShareholderWithdrawal.objects.filter(user=request.user)
        
        # Apply status filter
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Apply search (for superusers - search by user name/phone)
        if search and request.user.is_superuser:
            queryset = queryset.filter(
                Q(user__name__icontains=search) | Q(user__phone__icontains=search)
            )
        
        # Order by created_at (newest first)
        queryset = queryset.order_by('-created_at')
        
        # Paginate
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages
        
        if page > total_pages and total_pages > 0:
            page = total_pages
        if page < 1:
            page = 1
        
        page_obj = paginator.get_page(page)
        
        serializer = ShareholderWithdrawalSerializer(page_obj, many=True, context={'request': request})
        
        # Get counts by status
        pending_count = queryset.filter(status='pending').count()
        approved_count = queryset.filter(status='approved').count()
        failed_count = queryset.filter(status='failed').count()
        
        return Response({
            'withdrawals': serializer.data,
            'count': paginator.count,
            'page': page,
            'total_pages': total_pages,
            'page_size': page_size,
            'stats': {
                'pending': pending_count,
                'approved': approved_count,
                'failed': failed_count
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f'Error listing withdrawals: {str(e)}')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def withdrawal_create(request):
    """Create a new withdrawal request (for shareholders only)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_shareholder:
        return Response(
            {'error': 'Only shareholders can request withdrawals'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        amount = data.get('amount')
        remarks = data.get('remarks', '')
        
        if not amount:
            return Response(
                {'error': 'amount is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            amount = int(amount)
            if amount <= 0:
                return Response(
                    {'error': 'amount must be greater than 0'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except ValueError:
            return Response(
                {'error': 'amount must be a valid integer'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user has sufficient balance
        if amount > request.user.balance:
            return Response(
                {'error': f'Insufficient balance. Available: {request.user.balance}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if there's already a pending withdrawal
        pending_withdrawals = ShareholderWithdrawal.objects.filter(
            user=request.user,
            status='pending'
        ).exists()
        
        if pending_withdrawals:
            return Response(
                {'error': 'You already have a pending withdrawal request'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create withdrawal request
        withdrawal = ShareholderWithdrawal.objects.create(
            user=request.user,
            amount=amount,
            status='pending',
            remarks=remarks
        )
        
        serializer = ShareholderWithdrawalSerializer(withdrawal, context={'request': request})
        
        return Response({
            'message': 'Withdrawal request created successfully',
            'withdrawal': serializer.data
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f'Error creating withdrawal: {str(e)}')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def withdrawal_detail(request, id):
    """Get withdrawal request details"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        withdrawal = ShareholderWithdrawal.objects.get(id=id)
        
        # Check permissions
        if not request.user.is_superuser and withdrawal.user != request.user:
            return Response(
                {'error': 'You do not have permission to view this withdrawal'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ShareholderWithdrawalSerializer(withdrawal, context={'request': request})
        
        return Response({
            'withdrawal': serializer.data
        }, status=status.HTTP_200_OK)
        
    except ShareholderWithdrawal.DoesNotExist:
        return Response(
            {'error': 'Withdrawal not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f'Error getting withdrawal details: {str(e)}')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def withdrawal_approve(request, id):
    """Approve a withdrawal request (super admin only)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can approve withdrawals'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        withdrawal = ShareholderWithdrawal.objects.get(id=id)
        
        if withdrawal.status != 'pending':
            return Response(
                {'error': f'Cannot approve withdrawal with status: {withdrawal.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user still has sufficient balance
        if withdrawal.amount > withdrawal.user.balance:
            return Response(
                {'error': f'Insufficient balance. User balance: {withdrawal.user.balance}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update status to approved
        withdrawal.status = 'approved'
        withdrawal.save()
        
        # Create transaction and update balance
        # Note: Payment gateway integration would go here
        try:
            txn = process_shareholder_withdrawal(withdrawal)
            logger.info(f'Created withdrawal transaction #{txn.id} for withdrawal #{withdrawal.id}')
        except Exception as e:
            logger.error(f'Failed to create withdrawal transaction: {str(e)}')
            # Revert status on error
            withdrawal.status = 'pending'
            withdrawal.save()
            return Response(
                {'error': f'Failed to process withdrawal: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        serializer = ShareholderWithdrawalSerializer(withdrawal, context={'request': request})
        
        return Response({
            'message': 'Withdrawal approved successfully',
            'withdrawal': serializer.data,
            'new_balance': withdrawal.user.balance
        }, status=status.HTTP_200_OK)
        
    except ShareholderWithdrawal.DoesNotExist:
        return Response(
            {'error': 'Withdrawal not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f'Error approving withdrawal: {str(e)}')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def withdrawal_reject(request, id):
    """Reject a withdrawal request (super admin only)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can reject withdrawals'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        withdrawal = ShareholderWithdrawal.objects.get(id=id)
        
        if withdrawal.status != 'pending':
            return Response(
                {'error': f'Cannot reject withdrawal with status: {withdrawal.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        remarks = data.get('remarks', '')
        
        # Update status to failed
        withdrawal.status = 'failed'
        if remarks:
            withdrawal.remarks = (withdrawal.remarks or '') + f'\nRejection reason: {remarks}'
        withdrawal.save()
        
        serializer = ShareholderWithdrawalSerializer(withdrawal, context={'request': request})
        
        return Response({
            'message': 'Withdrawal rejected',
            'withdrawal': serializer.data
        }, status=status.HTTP_200_OK)
        
    except ShareholderWithdrawal.DoesNotExist:
        return Response(
            {'error': 'Withdrawal not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f'Error rejecting withdrawal: {str(e)}')
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
