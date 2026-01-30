from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
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
        country_code = data.get('country_code', '91')  # Default to India
        
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
        
        # Update country_code if provided (in case user changed it during login)
        if country_code and user.country_code != country_code:
            user.country_code = country_code
            user.save(update_fields=['country_code'])
        
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
        country_code = data.get('country_code', '91')  # Default to India
        
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
            country_code=country_code
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
        if 'country_code' in data:
            user.country_code = data.get('country_code')
        
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


@api_view(['POST'])
def save_fcm_token_by_phone(request):
    """
    Save FCM token by phone number (no authentication required)
    Used by Flutter app to register device tokens
    """
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
            return Response(
                {'error': 'Phone number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not fcm_token:
            return Response(
                {'error': 'FCM token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Find user by phone number
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist:
            return Response(
                {'error': 'User with this phone number does not exist'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if the same token already exists for this user
        existing_token = FcmToken.objects.filter(
            user=user,
            token=fcm_token
        ).first()
        
        if existing_token:
            # Token already exists, skip creating duplicate
            return Response({
                'message': 'FCM token already exists',
                'token_id': existing_token.id,
                'existing': True,
                'user_phone': user.phone
            }, status=status.HTTP_200_OK)
        
        # Create new FCM token entry (allows multiple devices per user)
        fcm_token_obj = FcmToken.objects.create(
            user=user,
            token=fcm_token
        )
        
        return Response({
            'message': 'FCM token saved successfully',
            'token_id': fcm_token_obj.id,
            'user_phone': user.phone
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def forgot_password(request):
    """
    Request OTP for password reset.
    Sends OTP to user's WhatsApp.
    """
    try:
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        phone = data.get('phone')
        country_code = data.get('country_code', '91')
        
        if not phone:
            return Response(
                {'error': 'Phone number is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user exists
        if not User.objects.filter(phone=phone).exists():
            return Response(
                {'error': 'No account found with this phone number'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Generate and send OTP
        from ..services.otp_service import generate_and_send_otp
        success, message = generate_and_send_otp(phone, country_code)
        
        if success:
            return Response({
                'message': message,
                'phone': phone,
                'country_code': country_code
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': message},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def verify_otp(request):
    """
    Verify OTP for password reset.
    """
    try:
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        phone = data.get('phone')
        country_code = data.get('country_code', '91')
        otp_code = data.get('otp')
        
        if not phone or not otp_code:
            return Response(
                {'error': 'Phone number and OTP are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify OTP
        from ..services.otp_service import verify_otp as verify_otp_service
        success, message = verify_otp_service(phone, country_code, otp_code)
        
        if success:
            return Response({
                'message': message,
                'verified': True,
                'phone': phone,
                'country_code': country_code
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': message, 'verified': False},
                status=status.HTTP_400_BAD_REQUEST
            )
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def reset_password(request):
    """
    Reset user password after OTP verification.
    """
    try:
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST
        
        phone = data.get('phone')
        country_code = data.get('country_code', '91')
        otp_code = data.get('otp')
        new_password = data.get('new_password')
        
        if not phone or not otp_code or not new_password:
            return Response(
                {'error': 'Phone, OTP, and new password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(new_password) < 6:
            return Response(
                {'error': 'Password must be at least 6 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify OTP first
        from ..services.otp_service import verify_otp as verify_otp_service
        success, message = verify_otp_service(phone, country_code, otp_code)
        
        if not success:
            return Response(
                {'error': message},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Find user and reset password
        try:
            user = User.objects.get(phone=phone)
            user.set_password(new_password)
            user.save(update_fields=['password'])
            
            return Response({
                'message': 'Password reset successfully. You can now login with your new password.'
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
