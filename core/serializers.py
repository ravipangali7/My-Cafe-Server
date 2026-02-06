from django.urls import reverse
from rest_framework import serializers
from .models import (
    User, Unit, Category, Product, ProductVariant,
    Order, OrderItem, Transaction, TransactionHistory, SuperSetting, QRStandOrder, Invoice,
    ShareholderWithdrawal, VendorCustomer, WhatsAppNotification
)


class UserSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    kyc_document_url = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'name', 'phone', 'country_code', 'logo_url', 'expire_date', 'is_active', 'is_online', 'is_superuser',
            'kyc_status', 'kyc_reject_reason', 'kyc_document_type', 'kyc_document_url',
            'subscription_start_date', 'subscription_end_date',
            'address', 'ug_api', 'balance', 'due_balance', 
            'is_shareholder', 'share_percentage',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo:
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        # No uploaded logo: return URL to auto-generated logo endpoint
        if request:
            return request.build_absolute_uri(reverse('vendor_logo_image', args=[obj.id]))
        return None
    
    def get_kyc_document_url(self, obj):
        if obj.kyc_document_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.kyc_document_file.url)
            return obj.kyc_document_file.url
        return None


class UnitSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Unit
        fields = ['id', 'name', 'symbol', 'user', 'user_info', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_info(self, obj):
        request = self.context.get('request')
        if request and request.user.is_superuser and obj.user:
            if obj.user.logo:
                if request:
                    return {
                        'id': obj.user.id,
                        'name': obj.user.name,
                        'phone': obj.user.phone,
                        'logo_url': request.build_absolute_uri(obj.user.logo.url)
                    }
                else:
                    return {
                        'id': obj.user.id,
                        'name': obj.user.name,
                        'phone': obj.user.phone,
                        'logo_url': obj.user.logo.url
                    }
            return {
                'id': obj.user.id,
                'name': obj.user.name,
                'phone': obj.user.phone,
                'logo_url': None
            }
        return None


class CategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    user_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = ['id', 'name', 'image_url', 'user', 'user_info', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None
    
    def get_user_info(self, obj):
        request = self.context.get('request')
        if request and request.user.is_superuser and obj.user:
            if obj.user.logo:
                if request:
                    return {
                        'id': obj.user.id,
                        'name': obj.user.name,
                        'phone': obj.user.phone,
                        'logo_url': request.build_absolute_uri(obj.user.logo.url)
                    }
                else:
                    return {
                        'id': obj.user.id,
                        'name': obj.user.name,
                        'phone': obj.user.phone,
                        'logo_url': obj.user.logo.url
                    }
            return {
                'id': obj.user.id,
                'name': obj.user.name,
                'phone': obj.user.phone,
                'logo_url': None
            }
        return None


class ProductVariantSerializer(serializers.ModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True)
    unit_symbol = serializers.CharField(source='unit.symbol', read_only=True)
    
    class Meta:
        model = ProductVariant
        fields = ['id', 'unit', 'unit_name', 'unit_symbol', 'price', 'discount_type', 'discount_value', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProductSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    user_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = ['id', 'name', 'image_url', 'category', 'category_name', 'type', 'is_active', 'variants', 'user', 'user_info', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None
    
    def get_user_info(self, obj):
        request = self.context.get('request')
        if request and request.user.is_superuser and obj.user:
            if obj.user.logo:
                if request:
                    return {
                        'id': obj.user.id,
                        'name': obj.user.name,
                        'phone': obj.user.phone,
                        'logo_url': request.build_absolute_uri(obj.user.logo.url)
                    }
                else:
                    return {
                        'id': obj.user.id,
                        'name': obj.user.name,
                        'phone': obj.user.phone,
                        'logo_url': obj.user.logo.url
                    }
            return {
                'id': obj.user.id,
                'name': obj.user.name,
                'phone': obj.user.phone,
                'logo_url': None
            }
        return None


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_image_url = serializers.SerializerMethodField()
    variant_info = serializers.SerializerMethodField()
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'product_image_url', 'product_variant', 'variant_info', 'price', 'quantity', 'total', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_product_image_url(self, obj):
        if obj.product and obj.product.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.product.image.url)
            return obj.product.image.url
        return None
    
    def get_variant_info(self, obj):
        if obj.product_variant:
            return {
                'unit_name': obj.product_variant.unit.name,
                'unit_symbol': obj.product_variant.unit.symbol,
                'price': str(obj.product_variant.price)
            }
        return None


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    vendor = serializers.SerializerMethodField()
    
    class Meta:
        model = Order
        fields = ['id', 'name', 'phone', 'country_code', 'table_no', 'status', 'payment_status', 'total', 'fcm_token', 'reject_reason', 'items', 'vendor', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_vendor(self, obj):
        if obj.user:
            vendor_data = {
                'id': obj.user.id,
                'name': obj.user.name,
                'phone': obj.user.phone,
                'logo_url': None
            }
            if obj.user.logo:
                request = self.context.get('request')
                if request:
                    vendor_data['logo_url'] = request.build_absolute_uri(obj.user.logo.url)
                else:
                    vendor_data['logo_url'] = obj.user.logo.url
            return vendor_data
        return None


class TransactionSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source='order.id', read_only=True, allow_null=True)
    qr_stand_order_id = serializers.IntegerField(source='qr_stand_order.id', read_only=True, allow_null=True)
    user_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'order', 'order_id', 'qr_stand_order', 'qr_stand_order_id',
            'user', 'user_info', 'amount', 'status', 'remarks', 
            'utr', 'vpa', 'payer_name', 'bank_id',
            'transaction_type', 'transaction_category', 'is_system',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_info(self, obj):
        request = self.context.get('request')
        if request and request.user.is_superuser and obj.user:
            if obj.user.logo:
                if request:
                    return {
                        'id': obj.user.id,
                        'name': obj.user.name,
                        'phone': obj.user.phone,
                        'logo_url': request.build_absolute_uri(obj.user.logo.url)
                    }
                else:
                    return {
                        'id': obj.user.id,
                        'name': obj.user.name,
                        'phone': obj.user.phone,
                        'logo_url': obj.user.logo.url
                    }
            return {
                'id': obj.user.id,
                'name': obj.user.name,
                'phone': obj.user.phone,
                'logo_url': None
            }
        return None


# Alias for backward compatibility
TransactionHistorySerializer = TransactionSerializer


class SuperSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuperSetting
        fields = [
            'id', 'expire_duration_month', 'per_qr_stand_price', 
            'subscription_fee_per_month',
            'ug_api', 'per_transaction_fee', 'is_subscription_fee',
            'due_threshold', 'is_whatsapp_usage', 'whatsapp_per_usage',
            'whatsapp_template_marketing', 'whatsapp_template_imagemarketing',
            'share_distribution_day', 'balance',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class KYCSerializer(serializers.ModelSerializer):
    """Serializer for KYC document submission"""
    kyc_document_url = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'name', 'phone', 'kyc_status', 'kyc_reject_reason',
            'kyc_document_type', 'kyc_document_file', 'kyc_document_url',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'kyc_status', 'kyc_reject_reason', 'created_at', 'updated_at']
    
    def get_kyc_document_url(self, obj):
        if obj.kyc_document_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.kyc_document_file.url)
            return obj.kyc_document_file.url
        return None


class QRStandOrderSerializer(serializers.ModelSerializer):
    vendor_info = serializers.SerializerMethodField()
    
    class Meta:
        model = QRStandOrder
        fields = [
            'id', 'vendor', 'vendor_info', 'quantity', 'total_price',
            'order_status', 'payment_status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_vendor_info(self, obj):
        if obj.vendor:
            vendor_data = {
                'id': obj.vendor.id,
                'name': obj.vendor.name,
                'phone': obj.vendor.phone,
                'logo_url': None
            }
            if obj.vendor.logo:
                request = self.context.get('request')
                if request:
                    vendor_data['logo_url'] = request.build_absolute_uri(obj.vendor.logo.url)
                else:
                    vendor_data['logo_url'] = obj.vendor.logo.url
            return vendor_data
        return None


class ShareholderSerializer(serializers.ModelSerializer):
    """Serializer for listing shareholders"""
    logo_url = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'name', 'phone', 'country_code', 'logo_url',
            'balance', 'due_balance', 'is_shareholder', 'share_percentage',
            'address', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo:
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        if request:
            return request.build_absolute_uri(reverse('vendor_logo_image', args=[obj.id]))
        return None


class ShareholderWithdrawalSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()
    
    class Meta:
        model = ShareholderWithdrawal
        fields = [
            'id', 'user', 'user_info', 'amount', 'status', 'remarks',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_user_info(self, obj):
        if obj.user:
            user_data = {
                'id': obj.user.id,
                'name': obj.user.name,
                'phone': obj.user.phone,
                'balance': obj.user.balance,
                'share_percentage': obj.user.share_percentage,
                'logo_url': None
            }
            if obj.user.logo:
                request = self.context.get('request')
                if request:
                    user_data['logo_url'] = request.build_absolute_uri(obj.user.logo.url)
                else:
                    user_data['logo_url'] = obj.user.logo.url
            return user_data
        return None


class VendorDueSerializer(serializers.ModelSerializer):
    """Serializer for listing vendors with dues"""
    logo_url = serializers.SerializerMethodField()
    is_over_threshold = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'name', 'phone', 'country_code', 'logo_url',
            'balance', 'due_balance', 'is_over_threshold',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_logo_url(self, obj):
        request = self.context.get('request')
        if obj.logo:
            if request:
                return request.build_absolute_uri(obj.logo.url)
            return obj.logo.url
        if request:
            return request.build_absolute_uri(reverse('vendor_logo_image', args=[obj.id]))
        return None
    
    def get_is_over_threshold(self, obj):
        threshold = self.context.get('due_threshold', 1000)
        return obj.due_balance > threshold


class VendorCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = VendorCustomer
        fields = ['id', 'name', 'phone', 'user', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class WhatsAppNotificationSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    customers_list = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppNotification
        fields = [
            'id', 'message', 'user', 'user_display', 'customers_list',
            'image', 'image_url', 'created_at', 'updated_at',
            'status', 'sent_count', 'total_count',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'status', 'sent_count', 'total_count']

    def get_user_display(self, obj):
        if obj.user:
            return {'id': obj.user.id, 'name': obj.user.name, 'phone': obj.user.phone}
        return None

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_customers_list(self, obj):
        return [
            {'id': c.id, 'name': c.name, 'phone': c.phone}
            for c in obj.customers.all()
        ]


class WhatsAppNotificationListSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppNotification
        fields = [
            'id', 'message', 'user', 'user_display', 'created_at', 'updated_at',
            'status', 'sent_count', 'total_count',
        ]

    def get_user_display(self, obj):
        if obj.user:
            return {'id': obj.user.id, 'name': obj.user.name}
        return None
