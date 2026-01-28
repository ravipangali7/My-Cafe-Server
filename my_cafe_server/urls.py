"""
URL configuration for my_cafe_server project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from core.views import (
    # Auth views
    login, register, logout, get_user, update_user, get_fcm_tokens, save_fcm_token, save_fcm_token_by_phone,
    # Dashboard
    dashboard_stats, vendor_dashboard_data, super_admin_dashboard_data,
    # Vendor views
    vendor_list, vendor_create, vendor_detail, vendor_edit, vendor_delete, vendor_logo_image,
    # Product views
    product_list, product_create, product_detail, product_edit, product_delete,
    # Category views
    category_list, category_create, category_detail, category_edit, category_delete,
    # Unit views
    unit_list, unit_create, unit_detail, unit_edit, unit_delete,
    # Order views
    order_list, order_create, order_detail, order_edit, order_delete,
    # Transaction views
    transaction_list, transaction_detail,
    # Settings views
    get_settings, update_settings, users_stats,
    # Stats views
    product_stats, order_stats, category_stats, transaction_stats, unit_stats, vendor_stats,
    # Report views
    cafe_report, order_report, product_report, finance_report,
    # Menu views
    menu_by_vendor_phone,
)

# Import new views
from core.views.kyc_views import kyc_status, kyc_submit, kyc_approve, kyc_reject, kyc_pending, kyc_list, kyc_detail
from core.views.menu_views import vendor_public_by_phone
from core.views.subscription_views import subscription_status, subscription_plans, subscription_subscribe, subscription_payment_success, subscription_transactions, subscription_history
from core.views.qr_stand_views import qr_stand_order_list, qr_stand_order_create, qr_stand_order_detail, qr_stand_order_update, qr_stand_order_delete
from core.views.qr_views import qr_generate, qr_download_pdf
from core.views.invoice_views import invoice_generate, invoice_download
from core.views.media_views import serve_media_cors

urlpatterns = [
    
    # Auth endpoints
    path('api/auth/login/', login, name='login'),
    # Register endpoint removed - registration now handled through vendor management
    path('api/auth/logout/', logout, name='logout'),
    path('api/auth/user/', get_user, name='get_user'),
    path('api/auth/user/update/', update_user, name='update_user'),
    path('api/auth/user/fcm-tokens/', get_fcm_tokens, name='get_fcm_tokens'),
    path('api/auth/user/fcm-token/', save_fcm_token, name='save_fcm_token'),
    path('api/fcm-token-by-phone/', save_fcm_token_by_phone, name='save_fcm_token_by_phone'),
    
    # Dashboard endpoints
    path('api/dashboard/stats', dashboard_stats, name='dashboard_stats'),  # No trailing slash to avoid redirect
    path('api/dashboard/stats/', dashboard_stats, name='dashboard_stats_slash'),
    path('api/dashboard/users-stats/', users_stats, name='users_stats'),
    path('api/dashboard/vendor-data/', vendor_dashboard_data, name='vendor_dashboard_data'),
    path('api/dashboard/super-admin-data/', super_admin_dashboard_data, name='super_admin_dashboard_data'),
    
    # Vendor endpoints
    path('api/vendors/', vendor_list, name='vendor_list'),
    path('api/vendors/create/', vendor_create, name='vendor_create'),
    path('api/vendors/<int:id>/', vendor_detail, name='vendor_detail'),
    path('api/vendors/<int:id>/logo/', vendor_logo_image, name='vendor_logo_image'),
    path('api/vendors/<int:id>/edit/', vendor_edit, name='vendor_edit'),
    path('api/vendors/<int:id>/delete/', vendor_delete, name='vendor_delete'),
    
    # Stats endpoints
    path('api/stats/products/', product_stats, name='product_stats'),
    path('api/stats/orders/', order_stats, name='order_stats'),
    path('api/stats/categories/', category_stats, name='category_stats'),
    path('api/stats/transactions/', transaction_stats, name='transaction_stats'),
    path('api/stats/units/', unit_stats, name='unit_stats'),
    path('api/stats/vendors/', vendor_stats, name='vendor_stats'),
    
    # Report endpoints
    path('api/reports/cafe', cafe_report, name='cafe_report'),  # No trailing slash to avoid redirect
    path('api/reports/cafe/', cafe_report, name='cafe_report_slash'),
    path('api/reports/orders/', order_report, name='order_report'),
    path('api/reports/products/', product_report, name='product_report'),
    path('api/reports/finance/', finance_report, name='finance_report'),
    
    # Product endpoints
    path('api/products/', product_list, name='product_list'),
    path('api/products/create/', product_create, name='product_create'),
    path('api/products/<int:id>/', product_detail, name='product_detail'),
    path('api/products/<int:id>/edit/', product_edit, name='product_edit'),
    path('api/products/<int:id>/delete/', product_delete, name='product_delete'),
    
    # Category endpoints
    path('api/categories/', category_list, name='category_list'),
    path('api/categories/create/', category_create, name='category_create'),
    path('api/categories/<int:id>/', category_detail, name='category_detail'),
    path('api/categories/<int:id>/edit/', category_edit, name='category_edit'),
    path('api/categories/<int:id>/delete/', category_delete, name='category_delete'),
    
    # Unit endpoints
    path('api/units/', unit_list, name='unit_list'),
    path('api/units/create/', unit_create, name='unit_create'),
    path('api/units/<int:id>/', unit_detail, name='unit_detail'),
    path('api/units/<int:id>/edit/', unit_edit, name='unit_edit'),
    path('api/units/<int:id>/delete/', unit_delete, name='unit_delete'),
    
    # Order endpoints
    path('api/orders/', order_list, name='order_list'),
    path('api/orders/create/', order_create, name='order_create'),
    path('api/orders/<int:id>/', order_detail, name='order_detail'),
    path('api/orders/<int:id>/edit/', order_edit, name='order_edit'),
    path('api/orders/<int:id>/delete/', order_delete, name='order_delete'),
    
    # Invoice endpoints
    path('api/orders/<int:order_id>/invoice/generate/', invoice_generate, name='invoice_generate'),
    path('api/orders/<int:order_id>/invoice/download/', invoice_download, name='invoice_download'),
    
    # Transaction endpoints
    path('api/transactions/', transaction_list, name='transaction_list'),
    path('api/transactions/<int:id>/', transaction_detail, name='transaction_detail'),
    
    # Settings endpoints
    path('api/settings/', get_settings, name='get_settings'),
    path('api/settings/update/', update_settings, name='update_settings'),
    
    # KYC endpoints
    path('api/kyc/status/', kyc_status, name='kyc_status'),
    path('api/kyc/submit/', kyc_submit, name='kyc_submit'),
    path('api/kyc/<int:id>/', kyc_detail, name='kyc_detail'),
    path('api/kyc/approve/<int:id>/', kyc_approve, name='kyc_approve'),
    path('api/kyc/reject/<int:id>/', kyc_reject, name='kyc_reject'),
    path('api/kyc/pending/', kyc_pending, name='kyc_pending'),
    path('api/kyc/list/', kyc_list, name='kyc_list'),
    
    # Subscription endpoints
    path('api/subscription/status/', subscription_status, name='subscription_status'),
    path('api/subscription/plans/', subscription_plans, name='subscription_plans'),
    path('api/subscription/subscribe/', subscription_subscribe, name='subscription_subscribe'),
    path('api/subscription/payment-success/', subscription_payment_success, name='subscription_payment_success'),
    path('api/subscription/transactions/', subscription_transactions, name='subscription_transactions'),
    path('api/subscription/history/', subscription_history, name='subscription_history'),
    
    # QR Stand Order endpoints
    path('api/qr-stands/orders/', qr_stand_order_list, name='qr_stand_order_list'),
    path('api/qr-stands/orders/create/', qr_stand_order_create, name='qr_stand_order_create'),
    path('api/qr-stands/orders/<int:id>/', qr_stand_order_detail, name='qr_stand_order_detail'),
    path('api/qr-stands/orders/<int:id>/update/', qr_stand_order_update, name='qr_stand_order_update'),
    path('api/qr-stands/orders/<int:id>/delete/', qr_stand_order_delete, name='qr_stand_order_delete'),
    
    # QR Generation endpoints
    path('api/qr/generate/<int:vendor_id>/', qr_generate, name='qr_generate'),
    path('api/qr/download-pdf/<int:vendor_id>/', qr_download_pdf, name='qr_download_pdf'),
    
    # Menu endpoints (public)
    path('api/menu/<str:vendor_phone>/', menu_by_vendor_phone, name='menu_by_vendor_phone'),
    path('api/public/vendor/<str:vendor_phone>/', vendor_public_by_phone, name='vendor_public_by_phone'),
    
    # Media with CORS (public, no auth) - so frontend can load logos/images cross-origin
    path('media/<path:path>', serve_media_cors, name='serve_media_cors'),
]

# Media is served by serve_media_cors above (CORS headers); do not add static(MEDIA_URL, MEDIA_ROOT).
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

urlpatterns.append(
    path('', admin.site.urls),
)