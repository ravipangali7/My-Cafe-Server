from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import json
from django.db.models import Q
from django.core.paginator import Paginator
from ..models import Unit
from ..serializers import UnitSerializer


@api_view(['GET'])
def unit_list(request):
    """Get all units for the authenticated user with filtering, search, and pagination"""
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
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
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
        
        # Apply search
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(symbol__icontains=search)
            )
        
        # Apply date filters
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)
        
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
        
        serializer = UnitSerializer(page_obj.object_list, many=True, context={'request': request})
        
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


@api_view(['POST'])
def unit_create(request):
    """Create a new unit"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        name = data.get('name')
        symbol = data.get('symbol')
        
        if not name or not symbol:
            return Response(
                {'error': 'Name and symbol are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        unit = Unit.objects.create(
            name=name,
            symbol=symbol,
            user=request.user
        )
        
        serializer = UnitSerializer(unit, context={'request': request})
        return Response({'unit': serializer.data}, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def unit_detail(request, id):
    """Get a specific unit"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can access any unit, regular users only their own
        if request.user.is_superuser:
            unit = Unit.objects.get(id=id)
        else:
            unit = Unit.objects.get(id=id, user=request.user)
        serializer = UnitSerializer(unit, context={'request': request})
        return Response({'unit': serializer.data}, status=status.HTTP_200_OK)
    except Unit.DoesNotExist:
        return Response(
            {'error': 'Unit not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
def unit_edit(request, id):
    """Update a unit"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can edit any unit, regular users only their own
        if request.user.is_superuser:
            unit = Unit.objects.get(id=id)
        else:
            unit = Unit.objects.get(id=id, user=request.user)
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        name = data.get('name')
        symbol = data.get('symbol')
        
        if name:
            unit.name = name
        if symbol:
            unit.symbol = symbol
        
        unit.save()
        
        serializer = UnitSerializer(unit, context={'request': request})
        return Response({'unit': serializer.data}, status=status.HTTP_200_OK)
        
    except Unit.DoesNotExist:
        return Response(
            {'error': 'Unit not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def unit_delete(request, id):
    """Delete a unit"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can delete any unit, regular users only their own
        if request.user.is_superuser:
            unit = Unit.objects.get(id=id)
        else:
            unit = Unit.objects.get(id=id, user=request.user)
        unit.delete()
        return Response({'message': 'Unit deleted successfully'}, status=status.HTTP_200_OK)
    except Unit.DoesNotExist:
        return Response(
            {'error': 'Unit not found'},
            status=status.HTTP_404_NOT_FOUND
        )
