"""
Transaction helper functions for creating single and dual transactions.

Dual Transaction Pattern:
When is_system=True, TWO transactions are created:
- If system receives money (system_direction='in'): User pays OUT, System gets IN
- If system gives money (system_direction='out'): System pays OUT, User gets IN

UG Payment Gateway Integration:
All transaction creation functions support UG-specific fields through **extra_fields:
- ug_order_id: UG Gateway order ID
- ug_client_txn_id: Unique transaction ID sent to UG
- ug_payment_url: Payment URL for redirect
- ug_txn_date: Transaction date for status check
- ug_status: UG payment status (created/scanning/success/failure)
- ug_remark: UG remark/message
"""

from decimal import Decimal
from ..models import Transaction, SuperSetting, User


def create_dual_transaction(
    user,
    amount,
    category,
    system_direction,
    remarks_user="",
    remarks_system="",
    order=None,
    qr_stand_order=None,
    status="success",
    **extra_fields
):
    """
    Create dual transactions for system-involved operations.
    
    Args:
        user: The vendor/user
        amount: Transaction amount (int or Decimal)
        category: Transaction category (e.g., 'transaction_fee', 'subscription_fee')
        system_direction: 'in' if system receives money, 'out' if system pays
        remarks_user: Remarks for user's transaction
        remarks_system: Remarks for system's transaction
        order: Order instance (optional)
        qr_stand_order: QRStandOrder instance (optional)
        status: Transaction status (default: 'success')
        **extra_fields: Additional fields like utr, vpa, payer_name, bank_id,
            ug_order_id, ug_client_txn_id, ug_payment_url, ug_txn_date, ug_status, ug_remark
    
    Returns:
        tuple: (txn_user, txn_system) - Both transaction instances
    """
    amount = Decimal(str(amount))
    
    if system_direction == 'in':
        # System receives money - User pays OUT, System gets IN
        user_type = 'out'
        system_type = 'in'
    else:
        # System gives money - System pays OUT, User gets IN
        user_type = 'in'
        system_type = 'out'
    
    # Transaction 1: User's perspective (is_system=False)
    txn_user = Transaction.objects.create(
        user=user,
        order=order,
        qr_stand_order=qr_stand_order,
        amount=amount,
        status=status,
        transaction_type=user_type,
        transaction_category=category,
        is_system=False,
        remarks=remarks_user,
        **extra_fields
    )
    
    # Transaction 2: System's perspective (is_system=True)
    txn_system = Transaction.objects.create(
        user=user,
        order=order,
        qr_stand_order=qr_stand_order,
        amount=amount,
        status=status,
        transaction_type=system_type,
        transaction_category=category,
        is_system=True,
        remarks=remarks_system,
        **extra_fields
    )
    
    return txn_user, txn_system


def create_single_transaction(
    user,
    amount,
    category,
    txn_type,
    order=None,
    qr_stand_order=None,
    status="success",
    remarks="",
    **extra_fields
):
    """
    Create a single transaction (non-system operations).
    
    Args:
        user: The vendor/user
        amount: Transaction amount (int or Decimal)
        category: Transaction category (e.g., 'order', 'share_withdrawal')
        txn_type: Transaction type ('in' or 'out')
        order: Order instance (optional)
        qr_stand_order: QRStandOrder instance (optional)
        status: Transaction status (default: 'success')
        remarks: Transaction remarks
        **extra_fields: Additional fields like utr, vpa, payer_name, bank_id,
            ug_order_id, ug_client_txn_id, ug_payment_url, ug_txn_date, ug_status, ug_remark
    
    Returns:
        Transaction: The created transaction instance
    """
    amount = Decimal(str(amount))
    
    txn = Transaction.objects.create(
        user=user,
        order=order,
        qr_stand_order=qr_stand_order,
        amount=amount,
        status=status,
        transaction_type=txn_type,
        transaction_category=category,
        is_system=False,
        remarks=remarks,
        **extra_fields
    )
    
    return txn


def update_system_balance(amount, operation='add'):
    """
    Update the system balance in SuperSettings.
    
    Args:
        amount: Amount to add or subtract
        operation: 'add' or 'subtract'
    
    Returns:
        int: New balance
    """
    settings = SuperSetting.objects.first()
    if not settings:
        return 0
    
    amount = int(amount)
    
    if operation == 'add':
        settings.balance += amount
    else:
        settings.balance -= amount
    
    settings.save()
    return settings.balance


def update_user_balance(user, amount, operation='add'):
    """
    Update user's balance.
    
    Args:
        user: User instance
        amount: Amount to add or subtract
        operation: 'add' or 'subtract'
    
    Returns:
        int: New balance
    """
    amount = int(amount)
    
    if operation == 'add':
        user.balance += amount
    else:
        user.balance -= amount
    
    user.save()
    return user.balance


def update_user_due_balance(user, amount, operation='add'):
    """
    Update user's due balance.
    
    Args:
        user: User instance
        amount: Amount to add or subtract
        operation: 'add' or 'subtract'
    
    Returns:
        int: New due balance
    """
    amount = int(amount)
    
    if operation == 'add':
        user.due_balance += amount
    else:
        user.due_balance -= amount
    
    user.save()
    return user.due_balance


def process_order_transactions(order, vendor, order_amount, transaction_fee, payment_data=None):
    """
    Process all transactions for an order.
    Creates order payment transaction and transaction fee dual transactions.
    
    Args:
        order: Order instance
        vendor: Vendor user instance
        order_amount: The order amount (without fee)
        transaction_fee: The transaction service fee
        payment_data: Optional dict with utr, vpa, payer_name, bank_id,
            and UG fields: ug_order_id, ug_client_txn_id, ug_payment_url, ug_txn_date, ug_status, ug_remark
    
    Returns:
        tuple: (order_txn, fee_txn_user, fee_txn_system)
    """
    payment_data = payment_data or {}
    
    # 1. Create Order Payment Transaction (Single - not system)
    order_txn = create_single_transaction(
        user=vendor,
        amount=order_amount,
        category='order',
        txn_type='in',
        order=order,
        remarks=f"Order #{order.id} payment from customer",
        **payment_data
    )
    
    # 2. Create Transaction Fee (Dual Transaction - system receives)
    fee_txn_user, fee_txn_system = create_dual_transaction(
        user=vendor,
        amount=transaction_fee,
        category='transaction_fee',
        system_direction='in',
        remarks_user=f"Transaction fee for Order #{order.id}",
        remarks_system=f"Transaction fee received for Order #{order.id}",
        order=order,
        **payment_data
    )
    
    # 3. Update vendor's due balance
    update_user_due_balance(vendor, transaction_fee, 'add')
    
    return order_txn, fee_txn_user, fee_txn_system


def process_qr_stand_payment(qr_order, payment_data=None):
    """
    Process QR stand order payment.
    Creates dual transactions and updates system balance.
    
    Args:
        qr_order: QRStandOrder instance
        payment_data: Optional dict with utr, vpa, payer_name, bank_id,
            and UG fields: ug_order_id, ug_client_txn_id, ug_payment_url, ug_txn_date, ug_status, ug_remark
    
    Returns:
        tuple: (txn_user, txn_system)
    """
    payment_data = payment_data or {}
    
    # Create dual transaction
    txn_user, txn_system = create_dual_transaction(
        user=qr_order.vendor,
        amount=qr_order.total_price,
        category='qr_stand_order',
        system_direction='in',
        remarks_user=f"QR Stand Order #{qr_order.id} payment",
        remarks_system=f"QR Stand Order #{qr_order.id} received",
        qr_stand_order=qr_order,
        **payment_data
    )
    
    # Update system balance
    update_system_balance(qr_order.total_price, 'add')
    
    return txn_user, txn_system


def process_subscription_payment(user, amount, months, payment_data=None):
    """
    Process subscription payment.
    Creates dual transactions and updates system balance.
    
    Args:
        user: User instance
        amount: Subscription amount
        months: Number of months
        payment_data: Optional dict with utr, vpa, payer_name, bank_id,
            and UG fields: ug_order_id, ug_client_txn_id, ug_payment_url, ug_txn_date, ug_status, ug_remark
    
    Returns:
        tuple: (txn_user, txn_system)
    """
    payment_data = payment_data or {}
    
    # Create dual transaction
    txn_user, txn_system = create_dual_transaction(
        user=user,
        amount=amount,
        category='subscription_fee',
        system_direction='in',
        remarks_user=f"Subscription payment for {months} month(s)",
        remarks_system=f"Subscription fee received from {user.name}",
        **payment_data
    )
    
    # Update system balance
    update_system_balance(amount, 'add')
    
    return txn_user, txn_system


def process_due_payment(vendor, amount, payment_data=None):
    """
    Process vendor due payment.
    Creates dual transactions and updates balances.
    
    Args:
        vendor: Vendor user instance
        amount: Payment amount
        payment_data: Optional dict with utr, vpa, payer_name, bank_id,
            and UG fields: ug_order_id, ug_client_txn_id, ug_payment_url, ug_txn_date, ug_status, ug_remark
    
    Returns:
        tuple: (txn_user, txn_system)
    """
    payment_data = payment_data or {}
    
    # Create dual transaction
    txn_user, txn_system = create_dual_transaction(
        user=vendor,
        amount=amount,
        category='due_paid',
        system_direction='in',
        remarks_user=f"Due payment of {amount}",
        remarks_system=f"Due payment received from {vendor.name}",
        **payment_data
    )
    
    # Update vendor's due balance
    update_user_due_balance(vendor, amount, 'subtract')
    
    # Update system balance
    update_system_balance(amount, 'add')
    
    return txn_user, txn_system


def process_share_distribution(shareholder, amount):
    """
    Process share distribution to a shareholder.
    Creates dual transactions and updates balances.
    
    Args:
        shareholder: Shareholder user instance
        amount: Distribution amount
    
    Returns:
        tuple: (txn_system, txn_user)
    """
    # Create dual transaction (system pays OUT, user gets IN)
    txn_user, txn_system = create_dual_transaction(
        user=shareholder,
        amount=amount,
        category='share_distribution',
        system_direction='out',
        remarks_user=f"Share distribution received",
        remarks_system=f"Share distribution to {shareholder.name}",
    )
    
    # Update shareholder balance
    update_user_balance(shareholder, amount, 'add')
    
    # Note: System balance is updated separately after all distributions
    
    return txn_system, txn_user


def process_shareholder_withdrawal(withdrawal):
    """
    Process approved shareholder withdrawal.
    Creates transaction and updates balance.
    
    Args:
        withdrawal: ShareholderWithdrawal instance
    
    Returns:
        Transaction: The withdrawal transaction
    """
    # Create single transaction (user withdraws OUT)
    txn = create_single_transaction(
        user=withdrawal.user,
        amount=withdrawal.amount,
        category='share_withdrawal',
        txn_type='out',
        remarks=f"Shareholder withdrawal #{withdrawal.id}",
    )
    
    # Update shareholder balance
    update_user_balance(withdrawal.user, withdrawal.amount, 'subtract')
    
    return txn


def process_whatsapp_usage(vendor, cost):
    """
    Process WhatsApp usage charge.
    Creates dual transactions and updates vendor's due balance.
    
    Args:
        vendor: Vendor user instance (or id)
        cost: WhatsApp message cost
    
    Returns:
        tuple: (txn_user, txn_system) or None if cost is 0
    """
    if cost <= 0:
        return None
    # Re-fetch user from DB so we use a fresh instance (avoids stale ref in background thread)
    try:
        vendor = User.objects.get(pk=vendor.pk)
    except (User.DoesNotExist, AttributeError):
        return None

    # Create dual transaction
    txn_user, txn_system = create_dual_transaction(
        user=vendor,
        amount=cost,
        category='whatsapp_usage',
        system_direction='in',
        remarks_user="WhatsApp usage charge",
        remarks_system=f"WhatsApp usage fee from {vendor.name}",
    )
    
    # Update vendor's due balance
    update_user_due_balance(vendor, cost, 'add')
    
    return txn_user, txn_system
