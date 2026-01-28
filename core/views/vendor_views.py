from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect
from datetime import timedelta
import json
from ..models import User, SuperSetting
from ..serializers import UserSerializer
from ..services.logo_service import generate_logo_image


@api_view(['GET'])
def vendor_list(request):
    """Get all vendors - all if superuser, own profile if not"""
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
        
        # If superuser, can see all vendors and filter by user_id
        if request.user.is_superuser:
            queryset = User.objects.all()
            if user_id:
                try:
                    queryset = queryset.filter(id=int(user_id))
                except ValueError:
                    pass
        else:
            # Regular users only see their own profile
            queryset = User.objects.filter(id=request.user.id)
        
        # Apply search filter
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(phone__icontains=search)
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
        
        serializer = UserSerializer(page_obj.object_list, many=True, context={'request': request})
        
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
def vendor_create(request):
    """Create a new vendor - superuser only"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only superusers can create vendors'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        name = data.get('name')
        phone = data.get('phone')
        password = data.get('password')
        email = data.get('email', '')
        is_superuser = data.get('is_superuser', 'false').lower() == 'true'
        is_active = data.get('is_active', 'true').lower() == 'true'
        expire_date = data.get('expire_date')
        token = data.get('token', '')
        
        if not name or not phone or not password:
            return Response(
                {'error': 'Name, phone, and password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user already exists
        if User.objects.filter(phone=phone).exists():
            return Response(
                {'error': 'User with this phone number already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create user
        user = User.objects.create_user(
            username=phone,
            phone=phone,
            name=name,
            email=email if email else f"{phone}@cafe.local",
            password=password,
            is_superuser=is_superuser,
            is_active=is_active
        )
        
        # Calculate expire_date from SuperSetting if not provided
        if not expire_date:
            try:
                super_setting = SuperSetting.objects.first()
                months = super_setting.expire_duration_month if super_setting else 12
                
                # Calculate expire_date = created_at + expire_duration_month months
                from datetime import date
                created_date = user.created_at.date()
                year = created_date.year
                month = created_date.month
                day = created_date.day
                
                # Add months
                month += months
                while month > 12:
                    month -= 12
                    year += 1
                
                # Handle day overflow (e.g., Jan 31 + 1 month = Feb 28/29)
                try:
                    user.expire_date = date(year, month, day)
                except ValueError:
                    # If day doesn't exist in target month (e.g., Feb 31), use last day of month
                    from calendar import monthrange
                    last_day = monthrange(year, month)[1]
                    user.expire_date = date(year, month, min(day, last_day))
            except Exception:
                # Fallback to 12 months if calculation fails
                from datetime import date
                created_date = user.created_at.date()
                year = created_date.year + 1
                month = created_date.month
                day = created_date.day
                try:
                    user.expire_date = date(year, month, day)
                except ValueError:
                    from calendar import monthrange
                    last_day = monthrange(year, month)[1]
                    user.expire_date = date(year, month, min(day, last_day))
        else:
            user.expire_date = expire_date
        
        if token:
            user.token = token
        
        # Handle logo file upload
        if 'logo' in request.FILES:
            user.logo = request.FILES['logo']
        
        user.save()
        
        serializer = UserSerializer(user, context={'request': request})
        return Response({
            'vendor': serializer.data,
            'message': 'Vendor created successfully'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def vendor_detail(request, id):
    """Get a specific vendor"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can see any vendor, regular users only their own
        if request.user.is_superuser:
            vendor = User.objects.get(id=id)
        else:
            # Regular users can only view their own profile
            if int(id) != request.user.id:
                return Response(
                    {'error': 'You can only view your own profile'},
                    status=status.HTTP_403_FORBIDDEN
                )
            vendor = request.user
        
        serializer = UserSerializer(vendor, context={'request': request})
        return Response({'vendor': serializer.data}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response(
            {'error': 'Vendor not found'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['PUT'])
def vendor_edit(request, id):
    """Update a vendor - superuser can edit any, regular users only their own"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Superusers can edit any vendor, regular users only their own
        if request.user.is_superuser:
            vendor = User.objects.get(id=id)
        else:
            if int(id) != request.user.id:
                return Response(
                    {'error': 'You can only edit your own profile'},
                    status=status.HTTP_403_FORBIDDEN
                )
            vendor = User.objects.get(id=id)
        
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        # Update fields if provided
        if 'name' in data:
            vendor.name = data.get('name')
        if 'phone' in data:
            new_phone = data.get('phone')
            # Check if phone is already taken by another user
            if User.objects.filter(phone=new_phone).exclude(id=vendor.id).exists():
                return Response(
                    {'error': 'Phone number already in use'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            vendor.phone = new_phone
            vendor.username = new_phone  # Keep username in sync
        if 'expire_date' in data:
            expire_date = data.get('expire_date')
            vendor.expire_date = expire_date if expire_date else None
        if 'token' in data:
            vendor.token = data.get('token')
        if 'is_active' in data:
            is_active_value = data.get('is_active')
            # Convert string "true"/"false" to boolean
            if isinstance(is_active_value, str):
                vendor.is_active = is_active_value.lower() in ('true', '1', 'yes')
            else:
                vendor.is_active = bool(is_active_value) if is_active_value is not None else True
        
        # Only superusers can change is_superuser and password
        if request.user.is_superuser:
            if 'is_superuser' in data:
                is_superuser_value = data.get('is_superuser', False)
                # Convert string "true"/"false" to boolean
                if isinstance(is_superuser_value, str):
                    vendor.is_superuser = is_superuser_value.lower() in ('true', '1', 'yes')
                else:
                    vendor.is_superuser = bool(is_superuser_value) if is_superuser_value is not None else False
            if 'password' in data and data.get('password'):
                vendor.set_password(data.get('password'))
        
        # Handle logo file upload
        if 'logo' in request.FILES:
            vendor.logo = request.FILES['logo']
        
        vendor.save()
        
        serializer = UserSerializer(vendor, context={'request': request})
        return Response({
            'vendor': serializer.data,
            'message': 'Vendor updated successfully'
        }, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response(
            {'error': 'Vendor not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def vendor_logo_image(request, id):
    """Serve vendor logo image: uploaded file or auto-generated from name."""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    try:
        if request.user.is_superuser:
            vendor = User.objects.get(id=id)
        else:
            if int(id) != request.user.id:
                return Response(
                    {'error': 'You can only access your own logo'},
                    status=status.HTTP_403_FORBIDDEN
                )
            vendor = request.user
    except User.DoesNotExist:
        return Response(
            {'error': 'Vendor not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    if vendor.logo:
        try:
            url = request.build_absolute_uri(vendor.logo.url)
            return redirect(url)
        except Exception:
            pass
    # No logo or file missing: generate from name
    buffer = generate_logo_image(vendor.name, size=(256, 256))
    return HttpResponse(buffer.getvalue(), content_type='image/png')


@api_view(['DELETE'])
def vendor_delete(request, id):
    """Delete a vendor - superuser only"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    if not request.user.is_superuser:
        return Response(
            {'error': 'Only superusers can delete vendors'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        vendor = User.objects.get(id=id)
        # Prevent deleting yourself
        if vendor.id == request.user.id:
            return Response(
                {'error': 'You cannot delete your own account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        vendor.delete()
        return Response({'message': 'Vendor deleted successfully'}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response(
            {'error': 'Vendor not found'},
            status=status.HTTP_404_NOT_FOUND
        )
