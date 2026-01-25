from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import json
from django.db.models import Q
from django.core.paginator import Paginator
from ..models import Category
from ..serializers import CategorySerializer


@api_view(['GET'])
def category_list(request):
    """Get all categories for the authenticated user with filtering, search, and pagination"""
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
        
        # Apply search
        if search:
            queryset = queryset.filter(name__icontains=search)
        
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
        
        serializer = CategorySerializer(page_obj.object_list, many=True, context={'request': request})
        
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
def category_create(request):
    """Create a new category"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        name = request.POST.get('name')
        image = request.FILES.get('image')
        
        if not name:
            return Response(
                {'error': 'Name is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        category = Category.objects.create(
            name=name,
            user=request.user
        )
        
        if image:
            category.image = image
            category.save()
        
        serializer = CategorySerializer(category, context={'request': request})
        return Response({'category': serializer.data}, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def category_detail(request, id):
    """Get a specific category"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can access any category, regular users only their own
        if request.user.is_superuser:
            category = Category.objects.get(id=id)
        else:
            category = Category.objects.get(id=id, user=request.user)
        serializer = CategorySerializer(category, context={'request': request})
        return Response({'category': serializer.data}, status=status.HTTP_200_OK)
    except Category.DoesNotExist:
        return Response(
            {'error': 'Category not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
def category_edit(request, id):
    """Update a category"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can edit any category, regular users only their own
        if request.user.is_superuser:
            category = Category.objects.get(id=id)
        else:
            category = Category.objects.get(id=id, user=request.user)
        
        name = request.POST.get('name')
        image = request.FILES.get('image')
        
        if name:
            category.name = name
        
        if image:
            category.image = image
        
        category.save()
        
        serializer = CategorySerializer(category, context={'request': request})
        return Response({'category': serializer.data}, status=status.HTTP_200_OK)
        
    except Category.DoesNotExist:
        return Response(
            {'error': 'Category not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def category_delete(request, id):
    """Delete a category"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can delete any category, regular users only their own
        if request.user.is_superuser:
            category = Category.objects.get(id=id)
        else:
            category = Category.objects.get(id=id, user=request.user)
        category.delete()
        return Response({'message': 'Category deleted successfully'}, status=status.HTTP_200_OK)
    except Category.DoesNotExist:
        return Response(
            {'error': 'Category not found'},
            status=status.HTTP_404_NOT_FOUND
        )
