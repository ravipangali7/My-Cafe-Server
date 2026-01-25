from django.contrib import admin
from .models import (
    User,
    FcmToken,
    Unit,
    Category,
    Product,
    ProductVariant,
    Order,
    OrderItem,
    TransactionHistory,
    SuperSetting
)


# --------------------
# Inline Admins
# --------------------
class FcmTokenInline(admin.StackedInline):
    model = FcmToken
    extra = 1


class ProductVariantInline(admin.StackedInline):
    model = ProductVariant
    extra = 1


class OrderItemInline(admin.StackedInline):
    model = OrderItem
    extra = 1


# --------------------
# Main Admins
# --------------------
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "phone", "expire_date", "is_active")
    inlines = [FcmTokenInline]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "is_active", "created_at")
    inlines = [ProductVariantInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "table_no", "status", "payment_status", "total")
    inlines = [OrderItemInline]


# --------------------
# Simple Registrations
# --------------------
admin.site.register(Unit)
admin.site.register(Category)
admin.site.register(TransactionHistory)
admin.site.register(SuperSetting)
