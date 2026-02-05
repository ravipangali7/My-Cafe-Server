from django.db import models
from django.contrib.auth.models import AbstractUser


# --------------------
# User Model
# --------------------
class User(AbstractUser):
    first_name = None
    last_name = None
    
    # KYC Status Choices
    KYC_PENDING = "pending"
    KYC_APPROVED = "approved"
    KYC_REJECTED = "rejected"
    
    KYC_STATUS_CHOICES = (
        (KYC_PENDING, "Pending"),
        (KYC_APPROVED, "Approved"),
        (KYC_REJECTED, "Rejected"),
    )
    
    # KYC Document Type Choices
    AADHAAR = "aadhaar"
    FOOD_LICENSE = "food_license"
    
    KYC_DOCUMENT_TYPE_CHOICES = (
        (AADHAAR, "Aadhaar Card"),
        (FOOD_LICENSE, "Food License"),
    )
    
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, unique=True)
    country_code = models.CharField(max_length=5, default='91')
    logo = models.ImageField(upload_to="logos/", blank=True, null=True)
    expire_date = models.DateField(null=True, blank=True)
    token = models.CharField(max_length=500, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # KYC Fields
    kyc_status = models.CharField(
        max_length=20, 
        choices=KYC_STATUS_CHOICES, 
        default=KYC_PENDING
    )
    kyc_reject_reason = models.TextField(blank=True, null=True)
    kyc_document_type = models.CharField(
        max_length=20, 
        choices=KYC_DOCUMENT_TYPE_CHOICES, 
        blank=True, 
        null=True
    )
    kyc_document_file = models.FileField(
        upload_to="kyc_documents/", 
        blank=True, 
        null=True
    )
    
    # Subscription Fields
    subscription_start_date = models.DateField(null=True, blank=True)
    subscription_end_date = models.DateField(null=True, blank=True)
    
    # New Balance & Shareholder Fields
    address = models.CharField(max_length=500, blank=True, default='')
    ug_api = models.CharField(max_length=255, blank=True, null=True)
    balance = models.IntegerField(default=0)
    due_balance = models.IntegerField(default=0)
    is_shareholder = models.BooleanField(default=False)
    share_percentage = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    USERNAME_FIELD = 'phone'
    
    def __str__(self):
        return f'{self.name} - ({self.phone})'

    def save(self, *args, **kwargs):
        # Automatically set username to phone value
        self.username = self.phone
        super().save(*args, **kwargs)

    def _str_(self):
        return f"{self.name or self.username} ({self.phone})"

    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_anonymous(self):
        return False



# --------------------
# FCM Token
# --------------------
class FcmToken(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, related_name="fcm_tokens", on_delete=models.CASCADE)
    token = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.token[:30]


# --------------------
# Unit
# --------------------
class Unit(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=10)
    user = models.ForeignKey(User, related_name="units", on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


# --------------------
# Category
# --------------------
class Category(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    user = models.ForeignKey(User, related_name="categories", on_delete=models.DO_NOTHING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


# --------------------
# Product
# --------------------
class Product(models.Model):
    VEG = "veg"
    NON_VEG = "non-veg"

    TYPE_CHOICES = (
        (VEG, "Veg"),
        (NON_VEG, "Non-Veg"),
    )

    id = models.BigAutoField(primary_key=True)
    category = models.ForeignKey(Category, related_name="products", on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name="products", on_delete=models.DO_NOTHING)
    name = models.CharField(max_length=200)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


# --------------------
# Product Variant
# --------------------
class ProductVariant(models.Model):
    PERCENTAGE = "percentage"
    FLAT = "flat"

    DISCOUNT_TYPE_CHOICES = (
        (PERCENTAGE, "Percentage"),
        (FLAT, "Flat"),
    )

    id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(Product, related_name="variants", on_delete=models.CASCADE)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_type = models.CharField(
        max_length=15, choices=DISCOUNT_TYPE_CHOICES, blank=True, null=True
    )
    discount_value = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.name} - {self.unit.symbol}"


# --------------------
# Order
# --------------------
class Order(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("running", "Running"),
        ("ready", "Ready"),
        ("rejected", "Rejected"),
        ("completed", "Completed"),
    )

    PAYMENT_STATUS_CHOICES = (
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
    )

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100)
    user = models.ForeignKey(User, related_name="orders", on_delete=models.DO_NOTHING)
    phone = models.CharField(max_length=15)
    country_code = models.CharField(max_length=5, default='91')
    table_no = models.CharField(max_length=10, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default="pending"
    )
    total = models.DecimalField(max_digits=12, decimal_places=2)
    fcm_token = models.TextField(blank=True, null=True)
    reject_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.id}"


# --------------------
# Order Item
# --------------------
class OrderItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    product_variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    total = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


# --------------------
# Transaction
# --------------------
class Transaction(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    )
    
    TRANSACTION_TYPE_CHOICES = (
        ("in", "In"),
        ("out", "Out"),
    )
    
    TRANSACTION_CATEGORY_CHOICES = (
        ("order", "Order Payment"),
        ("transaction_fee", "Transaction Fee"),
        ("subscription_fee", "Subscription Fee"),
        ("whatsapp_usage", "WhatsApp Usage"),
        ("qr_stand_order", "QR Stand Order"),
        ("share_distribution", "Share Distribution"),
        ("share_withdrawal", "Shareholder Withdrawal"),
        ("due_paid", "Due Paid"),
    )

    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(Order, related_name="transactions", on_delete=models.CASCADE, null=True, blank=True)
    qr_stand_order = models.ForeignKey('QRStandOrder', related_name="transactions", on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, related_name="transactions", on_delete=models.DO_NOTHING)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="success")
    remarks = models.TextField(blank=True, null=True)
    utr = models.CharField(max_length=100, blank=True, null=True)
    vpa = models.CharField(max_length=100, blank=True, null=True)
    payer_name = models.CharField(max_length=100, blank=True, null=True)
    bank_id = models.CharField(max_length=100, blank=True, null=True)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES, default="in")
    transaction_category = models.CharField(max_length=30, choices=TRANSACTION_CATEGORY_CHOICES, default="order")
    is_system = models.BooleanField(default=False)
    
    # UG Payment Gateway Fields
    ug_order_id = models.BigIntegerField(blank=True, null=True)
    ug_client_txn_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    ug_payment_url = models.URLField(max_length=500, blank=True, null=True)
    ug_txn_date = models.DateField(blank=True, null=True)
    ug_status = models.CharField(max_length=20, blank=True, null=True)
    ug_remark = models.TextField(blank=True, null=True)
    
    # Order payload for "initiate order payment" flow: order created only on payment success
    order_payload = models.JSONField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Transaction #{self.id} - {self.transaction_category} - {self.amount}"


# Keep TransactionHistory as alias for backward compatibility
TransactionHistory = Transaction


# --------------------
# Super Setting
# --------------------
class SuperSetting(models.Model):
    id = models.BigAutoField(primary_key=True)
    expire_duration_month = models.PositiveIntegerField()
    per_qr_stand_price = models.PositiveIntegerField(default=0)
    subscription_fee_per_month = models.PositiveIntegerField(default=0)
    
    # New Transaction System Fields
    ug_api = models.CharField(max_length=255, blank=True, null=True)
    per_transaction_fee = models.IntegerField(default=10)
    is_subscription_fee = models.BooleanField(default=True)
    due_threshold = models.IntegerField(default=1000)
    is_whatsapp_usage = models.BooleanField(default=True)
    whatsapp_per_usage = models.IntegerField(default=0)
    whatsapp_template_marketing = models.CharField(max_length=100, default='mycafemarketing', blank=True)
    whatsapp_template_imagemarketing = models.CharField(max_length=100, default='mycafeimagemarketing', blank=True)
    share_distribution_day = models.IntegerField(default=7)
    balance = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"SuperSetting (Balance: {self.balance})"


# --------------------
# QR Stand Order
# --------------------
class QRStandOrder(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("saved", "Saved"),
        ("delivered", "Delivered"),
    )

    PAYMENT_STATUS_CHOICES = (
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("failed", "Failed"),
    )

    id = models.BigAutoField(primary_key=True)
    vendor = models.ForeignKey(User, related_name="qr_stand_orders", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    total_price = models.DecimalField(max_digits=12, decimal_places=2)
    order_status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default="pending"
    )
    payment_status = models.CharField(
        max_length=20, 
        choices=PAYMENT_STATUS_CHOICES, 
        default="pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"QR Stand Order #{self.id} - {self.vendor.name}"


# --------------------
# Invoice
# --------------------
class Invoice(models.Model):
    id = models.BigAutoField(primary_key=True)
    order = models.OneToOneField(Order, related_name='invoice', on_delete=models.CASCADE)
    invoice_number = models.CharField(max_length=50, unique=True)
    pdf_file = models.FileField(upload_to='invoices/', blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Invoice #{self.invoice_number} - Order #{self.order.id}"


# --------------------
# OTP for Password Reset
# --------------------
class OTP(models.Model):
    id = models.BigAutoField(primary_key=True)
    phone = models.CharField(max_length=15)
    country_code = models.CharField(max_length=5, default='91')
    otp_code = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"OTP for {self.country_code}{self.phone}"
    
    class Meta:
        verbose_name = "OTP"
        verbose_name_plural = "OTPs"


# --------------------
# Shareholder Withdrawal
# --------------------
class ShareholderWithdrawal(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("failed", "Failed"),
    )
    
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, related_name="withdrawals", on_delete=models.CASCADE)
    amount = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Withdrawal #{self.id} - {self.user.name} - {self.amount}"
    
    class Meta:
        verbose_name = "Shareholder Withdrawal"
        verbose_name_plural = "Shareholder Withdrawals"


# --------------------
# Vendor Customer
# --------------------
class VendorCustomer(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15)
    user = models.ForeignKey(User, related_name="vendor_customers", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'phone')
        verbose_name = "Vendor Customer"
        verbose_name_plural = "Vendor Customers"

    def __str__(self):
        return f"{self.name} ({self.phone})"


# --------------------
# WhatsApp Notification
# --------------------
class WhatsAppNotification(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_SENDING = 'sending'
    STATUS_SENT = 'sent'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_SENDING, 'Sending'),
        (STATUS_SENT, 'Sent'),
        (STATUS_FAILED, 'Failed'),
    )

    id = models.BigAutoField(primary_key=True)
    message = models.TextField()
    user = models.ForeignKey(User, related_name='whatsapp_notifications', on_delete=models.CASCADE)
    customers = models.ManyToManyField(VendorCustomer, related_name='whatsapp_notifications', blank=True)
    image = models.ImageField(upload_to='whatsapp_notifications/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    sent_count = models.PositiveIntegerField(default=0)
    total_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'WhatsApp Notification'
        verbose_name_plural = 'WhatsApp Notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f"WhatsApp Notification #{self.id} - {self.user.name}"
