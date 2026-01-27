from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from ..models import User, FcmToken
from ..serializers import UserSerializer


@api_view(['POST'])
def login(request):
    """Login user with phone and password"""
    try:
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        phone = data.get('phone')
        password = data.get('password')
        
        if not phone or not password:
            return Response(
                {'error': 'Phone and password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = authenticate(request, username=phone, password=password)
        if user is None:
            return Response(
                {'error': 'Invalid phone or password'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        if not user.is_active:
            return Response(
                {'error': 'User account is disabled'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Create or get session
        from django.contrib.auth import login as django_login
        from datetime import date
        django_login(request, user)
        
        # Mark session as modified to ensure cookie is set
        request.session.modified = True
        # Explicitly save the session to ensure cookie is set
        request.session.save()
        
        # Check KYC status
        kyc_status = user.kyc_status
        kyc_approved = kyc_status == 'approved'
        
        # Check subscription status
        subscription_state = 'inactive'
        subscription_message = None
        today = date.today()
        
        if not user.subscription_end_date:
            subscription_state = 'no_subscription'
            subscription_message = 'No subscription found'
        elif user.subscription_end_date < today:
            subscription_state = 'expired'
            subscription_message = 'Subscription has expired'
        elif not user.is_active and user.subscription_end_date:
            subscription_state = 'inactive_with_date'
            subscription_message = 'Contact administrator'
        elif user.is_active and user.subscription_end_date and user.subscription_end_date >= today:
            subscription_state = 'active'
            subscription_message = 'Subscription is active'
        
        serializer = UserSerializer(user, context={'request': request})
        return Response({
            'user': serializer.data,
            'message': 'Login successful',
            'kyc_status': kyc_status,
            'kyc_approved': kyc_approved,
            'subscription_state': subscription_state,
            'subscription_message': subscription_message,
            'redirect_to_kyc': not kyc_approved,
            'redirect_to_subscription': kyc_approved and subscription_state in ['no_subscription', 'expired']
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def register(request):
    """Register a new user"""
    try:
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        name = data.get('name')
        phone = data.get('phone')
        password = data.get('password')
        email = data.get('email', '')
        
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
            password=password
        )
        
        # Login the user
        from django.contrib.auth import login as django_login
        django_login(request, user)
        
        # Explicitly save the session to ensure cookie is set
        request.session.save()
        
        serializer = UserSerializer(user, context={'request': request})
        return Response({
            'user': serializer.data,
            'message': 'Registration successful'
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def logout(request):
    """Logout current user"""
    from django.contrib.auth import logout as django_logout
    django_logout(request)
    return Response({'message': 'Logout successful'}, status=status.HTTP_200_OK)


@api_view(['GET'])
def get_user(request):
    """Get current authenticated user"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    serializer = UserSerializer(request.user, context={'request': request})
    return Response({'user': serializer.data}, status=status.HTTP_200_OK)


@api_view(['PUT'])
def update_user(request):
    """Update current user profile"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user = request.user
        
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        # Update fields if provided
        if 'name' in data:
            user.name = data.get('name')
        if 'phone' in data:
            new_phone = data.get('phone')
            # Check if phone is already taken by another user
            if User.objects.filter(phone=new_phone).exclude(id=user.id).exists():
                return Response(
                    {'error': 'Phone number already in use'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.phone = new_phone
            user.username = new_phone  # Keep username in sync
        if 'expire_date' in data:
            expire_date = data.get('expire_date')
            user.expire_date = expire_date if expire_date else None
        if 'token' in data:
            user.token = data.get('token')
        if 'is_active' in data:
            is_active_value = data.get('is_active')
            # Convert string "true"/"false" to boolean
            if isinstance(is_active_value, str):
                user.is_active = is_active_value.lower() in ('true', '1', 'yes')
            else:
                user.is_active = bool(is_active_value) if is_active_value is not None else True
        
        # Handle logo file upload
        if 'logo' in request.FILES:
            user.logo = request.FILES['logo']
        
        user.save()
        
        serializer = UserSerializer(user, context={'request': request})
        return Response({
            'user': serializer.data,
            'message': 'Profile updated successfully'
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def get_fcm_tokens(request):
    """Get FCM tokens for current user"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        fcm_tokens = FcmToken.objects.filter(user=request.user).order_by('-created_at')
        tokens_data = [
            {
                'id': token.id,
                'token': token.token,
                'created_at': token.created_at.isoformat(),
                'updated_at': token.updated_at.isoformat(),
            }
            for token in fcm_tokens
        ]
        return Response({'fcm_tokens': tokens_data}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def save_fcm_token(request):
    """Save FCM token for current user"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        token = data.get('token')
        
        if not token:
            return Response(
                {'error': 'FCM token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if the same token already exists for this user
        existing_token = FcmToken.objects.filter(
            user=request.user,
            token=token
        ).first()
        
        if existing_token:
            # Token already exists, skip creating duplicate
            return Response({
                'message': 'FCM token already exists',
                'token_id': existing_token.id,
                'existing': True
            }, status=status.HTTP_200_OK)
        
        # Create new FCM token entry (allows multiple devices per user)
        fcm_token = FcmToken.objects.create(
            user=request.user,
            token=token
        )
        
        return Response({
            'message': 'FCM token saved successfully',
            'token_id': fcm_token.id
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@csrf_exempt
def save_fcm_token_by_phone(request):
    """
    Save FCM token by phone number (no authentication required)
    Used by Flutter app to register device tokens
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Handle both JSON and form-data
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        phone = data.get('phone')
        fcm_token = data.get('fcm_token')
        
        # Validate required fields
        if not phone:
            return JsonResponse(
                {'error': 'Phone number is required'},
                status=400
            )
        
        if not fcm_token:
            return JsonResponse(
                {'error': 'FCM token is required'},
                status=400
            )
        
        # Find user by phone number
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            return JsonResponse(
                {'error': 'User with this phone number does not exist'},
                status=404
            )
        
        # Check if the same token already exists for this user
        existing_token = FcmToken.objects.filter(
            user=user,
            token=fcm_token
        ).first()
        
        if existing_token:
            # Token already exists, skip creating duplicate
            return JsonResponse({
                'message': 'FCM token already exists',
                'token_id': existing_token.id,
                'existing': True,
                'user_phone': user.phone
            }, status=200)
        
        # Create new FCM token entry (allows multiple devices per user)
        fcm_token_obj = FcmToken.objects.create(
            user=user,
            token=fcm_token
        )
        
        return JsonResponse({
            'message': 'FCM token saved successfully',
            'token_id': fcm_token_obj.id,
            'user_phone': user.phone
        }, status=201)
        
    except Exception as e:
        return JsonResponse(
            {'error': str(e)},
            status=500
        )
