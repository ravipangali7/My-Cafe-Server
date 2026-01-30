from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import json
from decimal import Decimal
from django.db.models import Q
from django.core.paginator import Paginator
from ..models import Product, ProductVariant, Category, Unit
from ..serializers import ProductSerializer, ProductVariantSerializer


@api_view(['GET'])
def product_list(request):
    """Get all products for the authenticated user with filtering, search, and pagination"""
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
        category_id = request.GET.get('category_id')
        is_active = request.GET.get('is_active')
        product_type = request.GET.get('type')
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
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
        
        # Apply filters
        if category_id:
            try:
                queryset = queryset.filter(category_id=int(category_id))
            except ValueError:
                pass
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        if product_type:
            queryset = queryset.filter(type=product_type)
        
        # Apply search
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(category__name__icontains=search)
            )
        
        # Apply date filters
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)
        
        # Select related and prefetch for performance
        queryset = queryset.select_related('category').prefetch_related('variants__unit').order_by('-created_at')
        
        # Paginate
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages
        
        if page > total_pages:
            page = total_pages
        if page < 1:
            page = 1
        
        page_obj = paginator.get_page(page)
        
        serializer = ProductSerializer(page_obj.object_list, many=True, context={'request': request})
        
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
def product_create(request):
    """Create a new product with variants"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        name = request.POST.get('name')
        category_id = request.POST.get('category_id')
        product_type = request.POST.get('type', 'veg')
        is_active = request.POST.get('is_active', 'true').lower() == 'true'
        image = request.FILES.get('image')
        variants_data = request.POST.get('variants', '[]')
        
        if not name or not category_id:
            return Response(
                {'error': 'Name and category_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            category = Category.objects.get(id=category_id, user=request.user)
        except Category.DoesNotExist:
            return Response(
                {'error': 'Category not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create product
        product = Product.objects.create(
            name=name,
            category=category,
            user=request.user,
            type=product_type,
            is_active=is_active
        )
        
        if image:
            product.image = image
            product.save()
        
        # Parse and create variants
        try:
            variants_list = json.loads(variants_data) if isinstance(variants_data, str) else variants_data
            for variant_data in variants_list:
                unit_id = variant_data.get('unit_id')
                price = variant_data.get('price')
                discount_type = variant_data.get('discount_type', '')
                discount_value = variant_data.get('discount_value', '0')
                
                if unit_id and price:
                    try:
                        unit = Unit.objects.get(id=unit_id, user=request.user)
                        ProductVariant.objects.create(
                            product=product,
                            unit=unit,
                            price=Decimal(str(price)),
                            discount_type=discount_type if discount_type else None,
                            discount_value=Decimal(str(discount_value))
                        )
                    except Unit.DoesNotExist:
                        continue
        except (json.JSONDecodeError, ValueError):
            pass
        
        serializer = ProductSerializer(product, context={'request': request})
        return Response({'product': serializer.data}, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def product_detail(request, id):
    """Get a specific product"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can access any product, regular users only their own
        if request.user.is_superuser:
            product = Product.objects.prefetch_related('variants__unit').get(id=id)
        else:
            product = Product.objects.prefetch_related('variants__unit').get(id=id, user=request.user)
        serializer = ProductSerializer(product, context={'request': request})
        return Response({'product': serializer.data}, status=status.HTTP_200_OK)
    except Product.DoesNotExist:
        return Response(
            {'error': 'Product not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
def product_edit(request, id):
    """Update a product"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can edit any product, regular users only their own
        if request.user.is_superuser:
            product = Product.objects.get(id=id)
        else:
            product = Product.objects.get(id=id, user=request.user)
        
        name = request.POST.get('name')
        category_id = request.POST.get('category_id')
        product_type = request.POST.get('type')
        is_active = request.POST.get('is_active')
        image = request.FILES.get('image')
        variants_data = request.POST.get('variants')
        
        if name:
            product.name = name
        if category_id:
            try:
                category = Category.objects.get(id=category_id, user=request.user)
                product.category = category
            except Category.DoesNotExist:
                return Response(
                    {'error': 'Category not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        if product_type:
            product.type = product_type
        if is_active is not None:
            product.is_active = is_active.lower() == 'true'
        if image:
            product.image = image
        
        product.save()
        
        # Update variants if provided
        if variants_data:
            try:
                # Delete existing variants
                ProductVariant.objects.filter(product=product).delete()
                
                # Create new variants
                variants_list = json.loads(variants_data) if isinstance(variants_data, str) else variants_data
                for variant_data in variants_list:
                    unit_id = variant_data.get('unit_id')
                    price = variant_data.get('price')
                    discount_type = variant_data.get('discount_type', '')
                    discount_value = variant_data.get('discount_value', '0')
                    
                    if unit_id and price:
                        try:
                            unit = Unit.objects.get(id=unit_id, user=request.user)
                            ProductVariant.objects.create(
                                product=product,
                                unit=unit,
                                price=Decimal(str(price)),
                                discount_type=discount_type if discount_type else None,
                                discount_value=Decimal(str(discount_value))
                            )
                        except Unit.DoesNotExist:
                            continue
            except (json.JSONDecodeError, ValueError):
                pass
        
        serializer = ProductSerializer(product, context={'request': request})
        return Response({'product': serializer.data}, status=status.HTTP_200_OK)
        
    except Product.DoesNotExist:
        return Response(
            {'error': 'Product not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def product_delete(request, id):
    """Delete a product"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can delete any product, regular users only their own
        if request.user.is_superuser:
            product = Product.objects.get(id=id)
        else:
            product = Product.objects.get(id=id, user=request.user)
        product.delete()
        return Response({'message': 'Product deleted successfully'}, status=status.HTTP_200_OK)
    except Product.DoesNotExist:
        return Response(
            {'error': 'Product not found'},
            status=status.HTTP_404_NOT_FOUND
        )
