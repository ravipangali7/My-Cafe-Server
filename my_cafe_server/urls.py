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
    forgot_password, verify_otp, reset_password,
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
    get_settings, update_settings, users_stats, get_public_settings,
    # Stats views
    product_stats, order_stats, category_stats, transaction_stats, unit_stats, vendor_stats, vendor_stats_by_id, qr_stand_stats,
    # Report views
    cafe_report, order_report, product_report, finance_report,
    vendor_report, shareholder_report, customer_report,
    # Menu views
    menu_by_vendor_phone,
)

# Import new views
from core.views.kyc_views import kyc_status, kyc_submit, kyc_approve, kyc_reject, kyc_pending, kyc_list, kyc_detail
from core.views.menu_views import vendor_public_by_phone
from core.views.subscription_views import subscription_status, subscription_plans, subscription_subscribe, subscription_payment_success, subscription_transactions, subscription_history
from core.views.qr_stand_views import qr_stand_order_list, qr_stand_order_create, qr_stand_order_detail, qr_stand_order_update, qr_stand_order_delete
from core.views.qr_views import qr_generate, qr_download_pdf, qr_card_download_png, qr_card_download_pdf
from core.views.invoice_views import invoice_generate, invoice_download, invoice_public_url, invoice_public_view, invoice_public_download
from core.views.shareholders_views import shareholders_list, shareholder_detail, shareholder_update
from core.views.withdrawals_views import withdrawals_list, withdrawal_create, withdrawal_detail, withdrawal_approve, withdrawal_reject, withdrawal_update, withdrawal_delete
from core.views.dues_views import dues_list, due_detail, due_pay, due_status
from core.views.payment_views import initiate_payment, initiate_order_payment, verify_payment, payment_callback, payment_status_by_order, payment_status_by_qr_stand
from core.views.vendor_customer_views import vendor_customer_list, vendor_customer_create, vendor_customer_detail, vendor_customer_edit, vendor_customer_delete
from core.views.whatsapp_notification_views import whatsapp_notification_list, whatsapp_notification_detail, whatsapp_notification_create

urlpatterns = [
    
    # Auth endpoints
    path('api/auth/login/', login, name='login'),
    path('api/auth/register/', register, name='register'),
    path('api/auth/logout/', logout, name='logout'),
    path('api/auth/user/', get_user, name='get_user'),
    path('api/auth/user/update/', update_user, name='update_user'),
    path('api/auth/user/fcm-tokens/', get_fcm_tokens, name='get_fcm_tokens'),
    path('api/auth/user/fcm-token/', save_fcm_token, name='save_fcm_token'),
    path('api/fcm-token-by-phone/', save_fcm_token_by_phone, name='save_fcm_token_by_phone'),
    
    # Password reset endpoints
    path('api/auth/forgot-password/', forgot_password, name='forgot_password'),
    path('api/auth/verify-otp/', verify_otp, name='verify_otp'),
    path('api/auth/reset-password/', reset_password, name='reset_password'),
    
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
    path('api/stats/vendor/<int:id>/', vendor_stats_by_id, name='vendor_stats_by_id'),
    path('api/stats/qr-stands/', qr_stand_stats, name='qr_stand_stats'),
    
    # Report endpoints
    path('api/reports/cafe', cafe_report, name='cafe_report'),  # No trailing slash to avoid redirect
    path('api/reports/cafe/', cafe_report, name='cafe_report_slash'),
    path('api/reports/orders/', order_report, name='order_report'),
    path('api/reports/products/', product_report, name='product_report'),
    path('api/reports/finance/', finance_report, name='finance_report'),
    path('api/reports/vendors/', vendor_report, name='vendor_report'),
    path('api/reports/shareholders/', shareholder_report, name='shareholder_report'),
    path('api/reports/customers/', customer_report, name='customer_report'),
    
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
    path('api/orders/<int:order_id>/invoice/public-url/', invoice_public_url, name='invoice_public_url'),
    # Public invoice endpoints (no authentication required)
    path('api/invoices/public/<int:order_id>/<str:token>/', invoice_public_view, name='invoice_public_view'),
    path('api/invoices/public/<int:order_id>/<str:token>/download/', invoice_public_download, name='invoice_public_download'),
    
    # Transaction endpoints
    path('api/transactions/', transaction_list, name='transaction_list'),
    path('api/transactions/<int:id>/', transaction_detail, name='transaction_detail'),
    
    # Settings endpoints
    path('api/settings/', get_settings, name='get_settings'),
    path('api/settings/update/', update_settings, name='update_settings'),
    path('api/settings/public/', get_public_settings, name='get_public_settings'),
    
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
    # QR card download (by vendor_phone, public)
    path('api/qr/card/download-png/<str:vendor_phone>/', qr_card_download_png, name='qr_card_download_png'),
    path('api/qr/card/download-pdf/<str:vendor_phone>/', qr_card_download_pdf, name='qr_card_download_pdf'),
    
    # Menu endpoints (public)
    path('api/menu/<str:vendor_phone>/', menu_by_vendor_phone, name='menu_by_vendor_phone'),
    path('api/public/vendor/<str:vendor_phone>/', vendor_public_by_phone, name='vendor_public_by_phone'),
    
    # Shareholders endpoints
    path('api/shareholders/', shareholders_list, name='shareholders_list'),
    path('api/shareholders/<int:id>/', shareholder_detail, name='shareholder_detail'),
    path('api/shareholders/<int:id>/update/', shareholder_update, name='shareholder_update'),
    
    # Withdrawals endpoints
    path('api/withdrawals/', withdrawals_list, name='withdrawals_list'),
    path('api/withdrawals/create/', withdrawal_create, name='withdrawal_create'),
    path('api/withdrawals/<int:id>/', withdrawal_detail, name='withdrawal_detail'),
    path('api/withdrawals/<int:id>/update/', withdrawal_update, name='withdrawal_update'),
    path('api/withdrawals/<int:id>/delete/', withdrawal_delete, name='withdrawal_delete'),
    path('api/withdrawals/<int:id>/approve/', withdrawal_approve, name='withdrawal_approve'),
    path('api/withdrawals/<int:id>/reject/', withdrawal_reject, name='withdrawal_reject'),
    
    # Dues endpoints
    path('api/dues/', dues_list, name='dues_list'),
    path('api/dues/status/', due_status, name='due_status'),
    path('api/dues/<int:id>/', due_detail, name='due_detail'),
    path('api/dues/pay/', due_pay, name='due_pay'),
    
    # Payment endpoints (UG Gateway)
    path('api/payment/initiate/', initiate_payment, name='initiate_payment'),
    path('api/payment/initiate-order/', initiate_order_payment, name='initiate_order_payment'),
    path('api/payment/verify/<str:client_txn_id>/', verify_payment, name='verify_payment'),
    path('api/payment/callback/', payment_callback, name='payment_callback'),
    path('api/payment/status/order/<int:order_id>/', payment_status_by_order, name='payment_status_by_order'),
    path('api/payment/status/qr-stand/<int:qr_stand_order_id>/', payment_status_by_qr_stand, name='payment_status_by_qr_stand'),
    
    # Vendor Customer endpoints
    path('api/vendor-customers/', vendor_customer_list, name='vendor_customer_list'),
    path('api/vendor-customers/create/', vendor_customer_create, name='vendor_customer_create'),
    path('api/vendor-customers/<int:id>/', vendor_customer_detail, name='vendor_customer_detail'),
    path('api/vendor-customers/<int:id>/edit/', vendor_customer_edit, name='vendor_customer_edit'),
    path('api/vendor-customers/<int:id>/delete/', vendor_customer_delete, name='vendor_customer_delete'),
    
    # WhatsApp Notifications (view-only list/detail, create with background send)
    path('api/whatsapp-notifications/', whatsapp_notification_list, name='whatsapp_notification_list'),
    path('api/whatsapp-notifications/create/', whatsapp_notification_create, name='whatsapp_notification_create'),
    path('api/whatsapp-notifications/<int:id>/', whatsapp_notification_detail, name='whatsapp_notification_detail'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

urlpatterns.append(
    path('', admin.site.urls),
)