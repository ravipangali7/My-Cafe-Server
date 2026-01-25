from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from ..models import User, Category, Product, ProductVariant
from ..serializers import CategorySerializer, ProductSerializer, ProductVariantSerializer, UserSerializer


@api_view(['GET'])
def menu_by_vendor_phone(request, vendor_phone):
    """Get menu (categories and products) for a vendor by phone number - public endpoint"""
    try:
        # Find vendor by phone
        try:
            vendor = User.objects.get(phone=vendor_phone, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get categories for this vendor
        categories = Category.objects.filter(user=vendor).order_by('name')
        
        # Get products for this vendor (only active products)
        products = Product.objects.filter(user=vendor, is_active=True).select_related('category').prefetch_related('variants__unit')
        
        # Group products by category
        categories_data = []
        for category in categories:
            category_products = products.filter(category=category)
            
            products_data = []
            for product in category_products:
                variants_data = []
                for variant in product.variants.all():
                    # Calculate discounted price
                    price = float(variant.price)
                    if variant.discount_type and variant.discount_value:
                        if variant.discount_type == 'percentage':
                            discounted_price = price * (1 - float(variant.discount_value) / 100)
                        else:  # flat
                            discounted_price = price - float(variant.discount_value)
                    else:
                        discounted_price = price
                    
                    variants_data.append({
                        'id': variant.id,
                        'unit_id': variant.unit.id,
                        'unit_name': variant.unit.name,
                        'unit_symbol': variant.unit.symbol,
                        'price': str(variant.price),
                        'discount_type': variant.discount_type,
                        'discount_value': str(variant.discount_value) if variant.discount_value else None,
                        'discounted_price': str(discounted_price),
                    })
                
                # Get product image URL
                image_url = None
                if product.image:
                    request_obj = request
                    if request_obj:
                        image_url = request_obj.build_absolute_uri(product.image.url)
                    else:
                        image_url = product.image.url
                
                products_data.append({
                    'id': product.id,
                    'name': product.name,
                    'type': product.type,
                    'image_url': image_url,
                    'variants': variants_data,
                })
            
            # Get category image URL
            category_image_url = None
            if category.image:
                request_obj = request
                if request_obj:
                    category_image_url = request_obj.build_absolute_uri(category.image.url)
                else:
                    category_image_url = category.image.url
            
            categories_data.append({
                'id': category.id,
                'name': category.name,
                'image_url': category_image_url,
                'products': products_data,
            })
        
        # Serialize vendor info
        vendor_serializer = UserSerializer(vendor, context={'request': request})
        
        return Response({
            'vendor': vendor_serializer.data,
            'categories': categories_data,
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
