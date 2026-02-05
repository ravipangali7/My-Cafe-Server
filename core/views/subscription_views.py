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
from ..utils.subscription_helpers import get_effective_subscription_end_date, get_subscription_state
# NOTE: process_subscription_payment is now called in payment_views.py on payment success

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
        effective_end = get_effective_subscription_end_date(user)
        subscription_state = get_subscription_state(user, today)
        is_active = subscription_state == 'active'
        message = {
            'no_subscription': 'No subscription found',
            'expired': 'Subscription has expired',
            'inactive_with_date': 'Contact administrator',
            'active': 'Subscription is active',
        }.get(subscription_state, 'Subscription is active')
        
        # Calculate subscription type (monthly or yearly) using effective end date or subscription dates
        subscription_type = None
        end_for_type = effective_end or user.subscription_end_date
        if user.subscription_start_date and end_for_type:
            months_diff = (end_for_type.year - user.subscription_start_date.year) * 12 + \
                         (end_for_type.month - user.subscription_start_date.month)
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
            'subscription_end_date': effective_end.isoformat() if effective_end else None,
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
    """
    DISABLED: Direct subscription activation is no longer allowed.
    Subscription must be purchased through UG payment flow.
    
    Use the following flow instead:
    1. POST /api/payment/initiate/ with payment_type='subscription'
    2. Complete payment on UG gateway
    3. Subscription will be activated automatically on payment success
    """
    return Response(
        {
            'error': 'Direct subscription is disabled. Please use UG payment flow.',
            'message': 'Use POST /api/payment/initiate/ with payment_type="subscription" to subscribe.',
            'payment_flow': {
                'step1': 'POST /api/payment/initiate/ with payment_type, reference_id (user_id), amount, customer_name, customer_mobile',
                'step2': 'Redirect user to payment_url received in response',
                'step3': 'Subscription activates automatically on successful payment'
            }
        },
        status=status.HTTP_400_BAD_REQUEST
    )


@api_view(['POST'])
def subscription_payment_success(request):
    """
    DISABLED: Direct payment success callback is no longer allowed.
    Payment verification is handled automatically through UG callback/verify endpoints.
    
    The UG payment callback (/api/payment/callback/) and verify endpoint (/api/payment/verify/)
    automatically handle subscription activation on successful payment.
    """
    return Response(
        {
            'error': 'Direct payment success callback is disabled.',
            'message': 'Payment verification is handled automatically through UG payment flow.',
            'info': 'Use GET /api/payment/verify/{txn_id}/ to check payment status.'
        },
        status=status.HTTP_400_BAD_REQUEST
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
        effective_end = get_effective_subscription_end_date(user)
        
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
        end_for_type = effective_end or user.subscription_end_date
        
        if user.subscription_start_date:
            # Calculate total amount paid
            total_amount = sum(float(t.amount) for t in transactions if t.status == 'success')
            
            # Determine subscription type using effective end date
            if end_for_type and user.subscription_start_date:
                months_diff = (end_for_type.year - user.subscription_start_date.year) * 12 + \
                             (end_for_type.month - user.subscription_start_date.month)
                subscription_type = 'yearly' if months_diff >= 12 else 'monthly'
            else:
                subscription_type = None
            
            history.append({
                'date': user.subscription_start_date.isoformat(),
                'event': 'subscription_started',
                'subscription_type': subscription_type,
                'start_date': user.subscription_start_date.isoformat(),
                'end_date': effective_end.isoformat() if effective_end else None,
                'amount_paid': str(total_amount),
                'status': 'active' if (effective_end and effective_end >= today) else 'expired'
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
                'end_date': effective_end.isoformat() if effective_end else None,
                'is_active': effective_end and effective_end >= today if effective_end else False
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
