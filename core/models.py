from django.db import models
from django.contrib.auth.models import AbstractUser


# --------------------
# User Model
# --------------------
class User(AbstractUser):
    first_name = None
    last_name = None
    
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, unique=True)
    logo = models.ImageField(upload_to="logos/", blank=True, null=True)
    expire_date = models.DateField(null=True, blank=True)
    token = models.CharField(max_length=500, null=True, blank=True)
    is_active = models.BooleanField(default=True)
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
    table_no = models.CharField(max_length=10)
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
# Transaction History
# --------------------
class TransactionHistory(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    )

    id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(Order, related_name="transactions", on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name="transactions", on_delete=models.DO_NOTHING)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    remarks = models.TextField(blank=True, null=True)
    utr = models.CharField(max_length=100, blank=True, null=True)
    vpa = models.CharField(max_length=100, blank=True, null=True)
    payer_name = models.CharField(max_length=100, blank=True, null=True)
    bank_id = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


# --------------------
# Super Setting
# --------------------
class SuperSetting(models.Model):
    id = models.BigAutoField(primary_key=True)
    expire_duration_month = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
