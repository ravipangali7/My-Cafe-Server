from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import json
from django.core.paginator import Paginator
from ..models import User
from ..serializers import UserSerializer, KYCSerializer


@api_view(['GET'])
def kyc_status(request):
    """Get current user's KYC status"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user = request.user
        serializer = UserSerializer(user, context={'request': request})
        
        # Check if document is submitted (has document type and file)
        has_document_submitted = bool(user.kyc_document_type and user.kyc_document_file)
        
        return Response({
            'kyc_status': user.kyc_status,
            'kyc_reject_reason': user.kyc_reject_reason,
            'kyc_document_type': user.kyc_document_type,
            'has_document_submitted': has_document_submitted,
            'user': serializer.data
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def kyc_submit(request):
    """Submit KYC documents (vendor only)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    # Only vendors can submit KYC (not superusers)
    if request.user.is_superuser:
        return Response(
            {'error': 'Super admins cannot submit KYC'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        user = request.user
        
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        kyc_document_type = data.get('kyc_document_type')
        
        # Validate document type
        if kyc_document_type not in [User.AADHAAR, User.FOOD_LICENSE]:
            return Response(
                {'error': 'Invalid document type. Must be "aadhaar" or "food_license"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if document file is provided
        if 'kyc_document_file' not in request.FILES:
            return Response(
                {'error': 'KYC document file is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update user KYC information
        user.kyc_document_type = kyc_document_type
        user.kyc_document_file = request.FILES['kyc_document_file']
        user.kyc_status = User.KYC_PENDING
        user.kyc_reject_reason = None  # Clear any previous rejection reason
        user.save()
        
        serializer = KYCSerializer(user, context={'request': request})
        return Response({
            'message': 'KYC documents submitted successfully',
            'kyc': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def kyc_approve(request, id):
    """Approve KYC (super admin only)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can approve KYC'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        user = User.objects.get(id=id)
        user.kyc_status = User.KYC_APPROVED
        user.kyc_reject_reason = None
        user.save()
        
        serializer = KYCSerializer(user, context={'request': request})
        return Response({
            'message': 'KYC approved successfully',
            'kyc': serializer.data
        }, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response(
            {'error': 'User not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def kyc_reject(request, id):
    """Reject KYC with reason (super admin only)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can reject KYC'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        reject_reason = data.get('reject_reason', '')
        
        if not reject_reason:
            return Response(
                {'error': 'Rejection reason is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = User.objects.get(id=id)
        user.kyc_status = User.KYC_REJECTED
        user.kyc_reject_reason = reject_reason
        user.save()
        
        serializer = KYCSerializer(user, context={'request': request})
        return Response({
            'message': 'KYC rejected',
            'kyc': serializer.data
        }, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response(
            {'error': 'User not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def kyc_pending(request):
    """List pending KYC (super admin only)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can view pending KYC'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Get query parameters
        search = request.GET.get('search', '').strip()
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))
        
        # Get pending KYC users
        queryset = User.objects.filter(kyc_status=User.KYC_PENDING)
        
        # Apply search filter
        if search:
            queryset = queryset.filter(
                name__icontains=search
            ) | queryset.filter(
                phone__icontains=search
            )
        
        # Order by created_at
        queryset = queryset.order_by('-created_at')
        
        # Paginate
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages
        
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1
        
        page_obj = paginator.get_page(page)
        
        serializer = KYCSerializer(page_obj, many=True, context={'request': request})
        
        return Response({
            'kyc_list': serializer.data,
            'count': paginator.count,
            'page': page,
            'total_pages': total_pages,
            'page_size': page_size
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def kyc_detail(request, id):
    """Get single KYC record by user id (super admin only)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can view KYC details'},
            status=status.HTTP_403_FORBIDDEN
        )
    try:
        user = User.objects.get(id=id)
        serializer = KYCSerializer(user, context={'request': request})
        return Response({'kyc': serializer.data}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response(
            {'error': 'KYC record not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def kyc_list(request):
    """List KYC with status filter (super admin only)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only super admins can view KYC list'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Get query parameters
        status_filter = request.GET.get('status', 'all').strip().lower()
        search = request.GET.get('search', '').strip()
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 10))
        
        # Get all users with KYC documents (exclude superusers)
        queryset = User.objects.filter(is_superuser=False)
        
        # Apply status filter
        if status_filter == 'pending':
            queryset = queryset.filter(kyc_status=User.KYC_PENDING)
        elif status_filter == 'approved':
            queryset = queryset.filter(kyc_status=User.KYC_APPROVED)
        elif status_filter == 'rejected':
            queryset = queryset.filter(kyc_status=User.KYC_REJECTED)
        # 'all' means no status filter
        
        # Apply search filter
        if search:
            queryset = queryset.filter(
                name__icontains=search
            ) | queryset.filter(
                phone__icontains=search
            )
        
        # Order by created_at
        queryset = queryset.order_by('-created_at')
        
        # Paginate
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages
        
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1
        
        page_obj = paginator.get_page(page)
        
        serializer = KYCSerializer(page_obj, many=True, context={'request': request})
        
        return Response({
            'kyc_list': serializer.data,
            'count': paginator.count,
            'page': page,
            'total_pages': total_pages,
            'page_size': page_size
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
