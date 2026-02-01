from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import IntegrityError
from django.core.paginator import Paginator
from ..models import VendorCustomer
from ..serializers import VendorCustomerSerializer


@api_view(['GET'])
def vendor_customer_list(request):
    """Get all vendor customers for the authenticated user with filtering, search, and pagination"""
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
        
        # Filter by user - superusers can see all customers and filter by user_id
        if request.user.is_superuser:
            queryset = VendorCustomer.objects.all()
            if user_id:
                try:
                    queryset = queryset.filter(user_id=int(user_id))
                except ValueError:
                    pass
        else:
            queryset = VendorCustomer.objects.filter(user=request.user)
        
        # Apply search (search by name or phone)
        if search:
            queryset = queryset.filter(
                name__icontains=search
            ) | queryset.filter(
                phone__icontains=search
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
        
        if page > total_pages and total_pages > 0:
            page = total_pages
        if page < 1:
            page = 1
        
        page_obj = paginator.get_page(page)
        
        serializer = VendorCustomerSerializer(page_obj.object_list, many=True, context={'request': request})
        
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
def vendor_customer_create(request):
    """Create a new vendor customer"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        name = request.POST.get('name') or request.data.get('name')
        phone = request.POST.get('phone') or request.data.get('phone')
        
        if not name:
            return Response(
                {'error': 'Name is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not phone:
            return Response(
                {'error': 'Phone is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Clean phone number (remove any non-digit characters except +)
        phone = ''.join(c for c in phone if c.isdigit() or c == '+')
        
        customer = VendorCustomer.objects.create(
            name=name,
            phone=phone,
            user=request.user
        )
        
        serializer = VendorCustomerSerializer(customer, context={'request': request})
        return Response({'customer': serializer.data}, status=status.HTTP_201_CREATED)
        
    except IntegrityError:
        return Response(
            {'error': 'A customer with this phone number already exists'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def vendor_customer_detail(request, id):
    """Get a specific vendor customer"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can access any customer, regular users only their own
        if request.user.is_superuser:
            customer = VendorCustomer.objects.get(id=id)
        else:
            customer = VendorCustomer.objects.get(id=id, user=request.user)
        serializer = VendorCustomerSerializer(customer, context={'request': request})
        return Response({'customer': serializer.data}, status=status.HTTP_200_OK)
    except VendorCustomer.DoesNotExist:
        return Response(
            {'error': 'Customer not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
def vendor_customer_edit(request, id):
    """Update a vendor customer"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can edit any customer, regular users only their own
        if request.user.is_superuser:
            customer = VendorCustomer.objects.get(id=id)
        else:
            customer = VendorCustomer.objects.get(id=id, user=request.user)
        
        name = request.POST.get('name') or request.data.get('name')
        phone = request.POST.get('phone') or request.data.get('phone')
        
        if name:
            customer.name = name
        
        if phone:
            # Clean phone number
            phone = ''.join(c for c in phone if c.isdigit() or c == '+')
            customer.phone = phone
        
        customer.save()
        
        serializer = VendorCustomerSerializer(customer, context={'request': request})
        return Response({'customer': serializer.data}, status=status.HTTP_200_OK)
        
    except VendorCustomer.DoesNotExist:
        return Response(
            {'error': 'Customer not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except IntegrityError:
        return Response(
            {'error': 'A customer with this phone number already exists'},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET', 'DELETE'])
def vendor_customer_delete(request, id):
    """Delete a vendor customer"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can delete any customer, regular users only their own
        if request.user.is_superuser:
            customer = VendorCustomer.objects.get(id=id)
        else:
            customer = VendorCustomer.objects.get(id=id, user=request.user)
        customer.delete()
        return Response({'message': 'Customer deleted successfully'}, status=status.HTTP_200_OK)
    except VendorCustomer.DoesNotExist:
        return Response(
            {'error': 'Customer not found'},
            status=status.HTTP_404_NOT_FOUND
        )
