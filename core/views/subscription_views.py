from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import json
import logging
from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Q
from ..models import User, SuperSetting, Transaction, TransactionHistory
from ..serializers import UserSerializer, TransactionHistorySerializer
from ..utils.transaction_helpers import process_subscription_payment

logger = logging.getLogger(__name__)


@api_view(['GET'])
def subscription_status(request):
    """Get subscription status for current user"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user = request.user
        today = date.today()
        
        # Check if subscription is active
        is_active = False
        if user.is_active and user.subscription_end_date:
            is_active = user.subscription_end_date >= today
        
        # Determine subscription state
        subscription_state = 'inactive'
        message = None
        
        if not user.subscription_end_date:
            # No subscription ever
            subscription_state = 'no_subscription'
            message = 'No subscription found'
        elif user.subscription_end_date < today:
            # Subscription expired
            subscription_state = 'expired'
            message = 'Subscription has expired'
        elif not user.is_active and user.subscription_end_date:
            # Subscription inactive but expire date exists
            subscription_state = 'inactive_with_date'
            message = 'Contact administrator'
        elif is_active:
            # Subscription is active
            subscription_state = 'active'
            message = 'Subscription is active'
        
        # Calculate subscription type (monthly or yearly)
        subscription_type = None
        if user.subscription_start_date and user.subscription_end_date:
            months_diff = (user.subscription_end_date.year - user.subscription_start_date.year) * 12 + \
                         (user.subscription_end_date.month - user.subscription_start_date.month)
            subscription_type = 'yearly' if months_diff >= 12 else 'monthly'
        
        # Get is_subscription_fee setting
        settings = SuperSetting.objects.first()
        is_subscription_fee = settings.is_subscription_fee if settings else True
        
        serializer = UserSerializer(user, context={'request': request})
        return Response({
            'subscription_state': subscription_state,
            'subscription_type': subscription_type,
            'is_active': is_active,
            'subscription_start_date': user.subscription_start_date.isoformat() if user.subscription_start_date else None,
            'subscription_end_date': user.subscription_end_date.isoformat() if user.subscription_end_date else None,
            'message': message,
            'is_subscription_fee': is_subscription_fee,
            'user': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def subscription_plans(request):
    """Get available subscription plans"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Get subscription fee from settings
        setting = SuperSetting.objects.first()
        subscription_fee_per_month = setting.subscription_fee_per_month if setting else 0
        
        # Define available plans
        plans = [
            {'id': 1, 'name': '1 Month', 'duration_months': 1},
            {'id': 2, 'name': '2 Months', 'duration_months': 2},
            {'id': 3, 'name': '3 Months', 'duration_months': 3},
            {'id': 4, 'name': '4 Months', 'duration_months': 4},
            {'id': 12, 'name': '1 Year', 'duration_months': 12},
            {'id': 24, 'name': '2 Years', 'duration_months': 24},
        ]
        
        # Calculate prices for each plan
        for plan in plans:
            plan['price'] = subscription_fee_per_month * plan['duration_months']
            plan['price_per_month'] = subscription_fee_per_month
        
        return Response({
            'plans': plans,
            'subscription_fee_per_month': subscription_fee_per_month
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def subscription_subscribe(request):
    """Create subscription after payment"""
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
        
        plan_id = data.get('plan_id')
        duration_months = data.get('duration_months')
        payment_amount = data.get('payment_amount')
        payment_transaction_id = data.get('payment_transaction_id', '')
        
        if not plan_id or not duration_months or not payment_amount:
            return Response(
                {'error': 'plan_id, duration_months, and payment_amount are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = request.user
        today = date.today()
        
        # Calculate subscription dates
        # If user already has a subscription, extend from end date
        # Otherwise, start from today
        if user.subscription_end_date and user.subscription_end_date >= today:
            # Extend existing subscription
            start_date = user.subscription_start_date or today
            end_date = user.subscription_end_date
        else:
            # New subscription
            start_date = today
            end_date = today
        
        # Add months to end date
        year = end_date.year
        month = end_date.month + int(duration_months)
        
        # Handle year overflow
        while month > 12:
            month -= 12
            year += 1
        
        # Handle day overflow (e.g., Jan 31 + 1 month = Feb 28/29)
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        day = min(end_date.day, last_day)
        
        try:
            new_end_date = date(year, month, day)
        except ValueError:
            new_end_date = date(year, month, last_day)
        
        # Update user subscription
        user.subscription_start_date = start_date
        user.subscription_end_date = new_end_date
        user.expire_date = new_end_date  # Also update expire_date to match subscription_end_date
        user.is_active = True
        user.save()
        
        # Create dual transaction for subscription payment
        # User pays OUT, System receives IN
        payment_data = {}
        if payment_transaction_id:
            payment_data['utr'] = payment_transaction_id
        
        try:
            txn_user, txn_system = process_subscription_payment(
                user=user,
                amount=payment_amount,
                months=int(duration_months),
                payment_data=payment_data if payment_data else None
            )
            transaction_id = txn_user.id
            logger.info(f'Created subscription transactions for user {user.id}')
        except Exception as e:
            logger.error(f'Failed to create subscription transactions: {str(e)}')
            transaction_id = None
        
        serializer = UserSerializer(user, context={'request': request})
        return Response({
            'message': 'Subscription activated successfully',
            'subscription_start_date': start_date.isoformat(),
            'subscription_end_date': new_end_date.isoformat(),
            'transaction_id': transaction_id,
            'user': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
def subscription_payment_success(request):
    """Handle payment success callback"""
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
        
        payment_transaction_id = data.get('payment_transaction_id')
        plan_id = data.get('plan_id')
        duration_months = data.get('duration_months')
        payment_amount = data.get('payment_amount')
        
        if not payment_transaction_id:
            return Response(
                {'error': 'payment_transaction_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # This endpoint can be used to verify payment and activate subscription
        # For now, it's similar to subscribe endpoint
        # In production, you would verify the payment with payment gateway first
        
        user = request.user
        today = date.today()
        
        # Calculate subscription dates
        if user.subscription_end_date and user.subscription_end_date >= today:
            start_date = user.subscription_start_date or today
            end_date = user.subscription_end_date
        else:
            start_date = today
            end_date = today
        
        # Add months
        months = int(duration_months) if duration_months else 1
        year = end_date.year
        month = end_date.month + months
        
        while month > 12:
            month -= 12
            year += 1
        
        from calendar import monthrange
        last_day = monthrange(year, month)[1]
        day = min(end_date.day, last_day)
        
        try:
            new_end_date = date(year, month, day)
        except ValueError:
            new_end_date = date(year, month, last_day)
        
        # Update user
        user.subscription_start_date = start_date
        user.subscription_end_date = new_end_date
        user.expire_date = new_end_date  # Also update expire_date to match subscription_end_date
        user.is_active = True
        user.save()
        
        # Create dual transaction for subscription payment
        payment_data = {'utr': payment_transaction_id}
        
        try:
            txn_user, txn_system = process_subscription_payment(
                user=user,
                amount=payment_amount or 0,
                months=months,
                payment_data=payment_data
            )
            logger.info(f'Created subscription transactions for user {user.id}')
        except Exception as e:
            logger.error(f'Failed to create subscription transactions: {str(e)}')
        
        serializer = UserSerializer(user, context={'request': request})
        return Response({
            'message': 'Payment successful and subscription activated',
            'subscription_start_date': start_date.isoformat(),
            'subscription_end_date': new_end_date.isoformat(),
            'user': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def subscription_transactions(request):
    """Get all subscription-related transactions for the current user"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Get subscription-related transactions 
        # Filter by transaction_category = 'subscription_fee' OR legacy (order is None and remarks contain 'Subscription')
        transactions = Transaction.objects.filter(
            user=request.user,
            is_system=False  # Only show user's transactions, not system records
        ).filter(
            Q(transaction_category='subscription_fee') |
            (Q(order__isnull=True) & (Q(remarks__icontains='Subscription') | Q(remarks__icontains='subscription')))
        ).order_by('-created_at')
        
        serializer = TransactionHistorySerializer(transactions, many=True, context={'request': request})
        
        return Response({
            'transactions': serializer.data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def subscription_history(request):
    """Get subscription timeline with payment history"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        user = request.user
        today = date.today()
        
        # Get subscription transactions (user's transactions, not system)
        transactions = Transaction.objects.filter(
            user=user,
            is_system=False
        ).filter(
            Q(transaction_category='subscription_fee') |
            (Q(order__isnull=True) & (Q(remarks__icontains='Subscription') | Q(remarks__icontains='subscription')))
        ).order_by('created_at')
        
        # Build history timeline
        history = []
        
        if user.subscription_start_date:
            # Calculate total amount paid
            total_amount = sum(float(t.amount) for t in transactions if t.status == 'success')
            
            # Determine subscription type
            if user.subscription_end_date and user.subscription_start_date:
                months_diff = (user.subscription_end_date.year - user.subscription_start_date.year) * 12 + \
                             (user.subscription_end_date.month - user.subscription_start_date.month)
                subscription_type = 'yearly' if months_diff >= 12 else 'monthly'
            else:
                subscription_type = None
            
            history.append({
                'date': user.subscription_start_date.isoformat(),
                'event': 'subscription_started',
                'subscription_type': subscription_type,
                'start_date': user.subscription_start_date.isoformat(),
                'end_date': user.subscription_end_date.isoformat() if user.subscription_end_date else None,
                'amount_paid': str(total_amount),
                'status': 'active' if (user.subscription_end_date and user.subscription_end_date >= today) else 'expired'
            })
            
            # Add transaction events
            for transaction in transactions:
                history.append({
                    'date': transaction.created_at.date().isoformat(),
                    'event': 'payment',
                    'amount': str(transaction.amount),
                    'status': transaction.status,
                    'utr': transaction.utr,
                    'remarks': transaction.remarks
                })
        
        return Response({
            'history': history,
            'current_subscription': {
                'start_date': user.subscription_start_date.isoformat() if user.subscription_start_date else None,
                'end_date': user.subscription_end_date.isoformat() if user.subscription_end_date else None,
                'is_active': user.subscription_end_date and user.subscription_end_date >= today if user.subscription_end_date else False
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
