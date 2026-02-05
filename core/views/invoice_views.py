"""
Invoice views for generating and downloading PDF bills
"""
import hmac
import hashlib
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.conf import settings
from django.db.models import Sum
from datetime import datetime
from ..models import Order, Invoice
from ..services.pdf_service import generate_order_invoice


# Secret key for generating public invoice tokens
INVOICE_TOKEN_SECRET = getattr(settings, 'INVOICE_TOKEN_SECRET', settings.SECRET_KEY)


def generate_invoice_token(order_id: int) -> str:
    """Generate a secure token for public invoice access using HMAC."""
    message = f"invoice-{order_id}".encode('utf-8')
    token = hmac.new(
        INVOICE_TOKEN_SECRET.encode('utf-8'),
        message,
        hashlib.sha256
    ).hexdigest()[:32]  # Use first 32 chars for shorter URL
    return token


def verify_invoice_token(order_id: int, token: str) -> bool:
    """Verify that the token is valid for the given order_id."""
    expected_token = generate_invoice_token(order_id)
    return hmac.compare_digest(token, expected_token)


def _get_order_payment_method(order) -> str:
    """Derive payment method from order's transactions (Order model has no payment_method field)."""
    txn = order.transactions.filter(status='success').first()
    if not txn:
        return "Pending"
    if getattr(txn, 'ug_order_id', None):
        return "Online"
    if getattr(txn, 'vpa', None) and txn.vpa:
        return "UPI"
    return "Other"


@api_view(['POST', 'GET'])
def invoice_generate(request, order_id):
    """
    Generate PDF invoice for an order.
    If invoice already exists, return existing invoice data.
    """
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Get order - superusers can access any order, regular users only their own
        if request.user.is_superuser:
            order = Order.objects.prefetch_related('items__product', 'items__product_variant__unit').get(id=order_id)
        else:
            order = Order.objects.prefetch_related('items__product', 'items__product_variant__unit').get(id=order_id, user=request.user)
        
        # Check if invoice already exists
        invoice, created = Invoice.objects.get_or_create(
            order=order,
            defaults={
                'invoice_number': f'INV-{order.id}-{datetime.now().strftime("%Y%m%d%H%M%S")}',
                'total_amount': order.total
            }
        )
        
        # Update total amount if order total changed
        if invoice.total_amount != order.total:
            invoice.total_amount = order.total
            invoice.save()
        
        # If invoice exists but PDF is missing, regenerate it
        if not invoice.pdf_file or not invoice.pdf_file.name:
            # Generate PDF
            pdf_file = generate_order_invoice(order)
            
            # Save PDF to invoice
            invoice.pdf_file.save(
                pdf_file.name,
                pdf_file,
                save=True
            )
            invoice.total_amount = order.total
            invoice.save()
        
        # Build download URL
        request_obj = request
        pdf_url = None
        if invoice.pdf_file:
            if request_obj:
                pdf_url = request_obj.build_absolute_uri(invoice.pdf_file.url)
            else:
                pdf_url = invoice.pdf_file.url
        
        return Response({
            'invoice': {
                'id': invoice.id,
                'invoice_number': invoice.invoice_number,
                'order_id': order.id,
                'total_amount': str(invoice.total_amount),
                'pdf_url': pdf_url,
                'generated_at': invoice.generated_at.isoformat(),
                'created': created
            }
        }, status=status.HTTP_200_OK)
        
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def invoice_download(request, order_id):
    """
    Download PDF invoice for an order.
    """
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Get order - superusers can access any order, regular users only their own
        if request.user.is_superuser:
            order = Order.objects.get(id=order_id)
        else:
            order = Order.objects.get(id=order_id, user=request.user)
        
        # Get or create invoice
        try:
            invoice = Invoice.objects.get(order=order)
        except Invoice.DoesNotExist:
            # Generate invoice if it doesn't exist
            invoice, _ = Invoice.objects.get_or_create(
                order=order,
                defaults={
                    'invoice_number': f'INV-{order.id}-{datetime.now().strftime("%Y%m%d%H%M%S")}',
                    'total_amount': order.total
                }
            )
            
            # Generate PDF
            pdf_file = generate_order_invoice(order)
            invoice.pdf_file.save(
                pdf_file.name,
                pdf_file,
                save=True
            )
            invoice.total_amount = order.total
            invoice.save()
        
        # Check if PDF file exists
        if not invoice.pdf_file or not invoice.pdf_file.name:
            # Generate PDF if missing
            pdf_file = generate_order_invoice(order)
            invoice.pdf_file.save(
                pdf_file.name,
                pdf_file,
                save=True
            )
            invoice.total_amount = order.total
            invoice.save()
        
        # Return PDF from memory so response is independent of storage/file handle lifecycle
        try:
            with invoice.pdf_file.open('rb') as f:
                pdf_bytes = f.read()
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="invoice_order_{order.id}.pdf"'
            return response
        except Exception as e:
            return Response(
                {'error': f'Failed to read PDF file: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def invoice_public_url(request, order_id):
    """
    Generate a public URL for accessing an invoice without authentication.
    This endpoint requires authentication to get the public URL.
    """
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Get order - superusers can access any order, regular users only their own
        if request.user.is_superuser:
            order = Order.objects.get(id=order_id)
        else:
            order = Order.objects.get(id=order_id, user=request.user)
        
        # Generate secure token
        token = generate_invoice_token(order_id)
        
        # Build the public URL (React/frontend page URL, not API endpoint)
        # Use configured frontend base URL so the link opens the React app, not the API host
        frontend_base = getattr(settings, 'FRONTEND_BASE_URL', None) or getattr(settings, 'PAYMENT_REDIRECT_BASE_URL', '')
        if not frontend_base:
            frontend_base = request.build_absolute_uri('/').rstrip('/').replace('/api', '')
        public_url = f"{frontend_base.rstrip('/')}/invoice/public/{order_id}/{token}"
        
        return Response({
            'url': public_url,
            'order_id': order_id,
            'token': token
        }, status=status.HTTP_200_OK)
        
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def invoice_public_view(request, order_id, token):
    """
    Public endpoint to view invoice data without authentication.
    Token is verified using HMAC to ensure the request is valid.
    Returns invoice data as JSON (for the React public page to render).
    """
    # Verify token
    if not verify_invoice_token(order_id, token):
        return Response(
            {'error': 'Invalid or expired token'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Get order with related data (prefetch transactions for payment_method derivation)
        order = Order.objects.prefetch_related(
            'items__product',
            'items__product_variant__unit',
            'user',
            'transactions',
        ).get(id=order_id)
        
        # Get or create invoice
        invoice, created = Invoice.objects.get_or_create(
            order=order,
            defaults={
                'invoice_number': f'INV-{order.id}-{datetime.now().strftime("%Y%m%d%H%M%S")}',
                'total_amount': order.total
            }
        )
        
        # Generate PDF if missing
        if not invoice.pdf_file or not invoice.pdf_file.name:
            pdf_file = generate_order_invoice(order)
            invoice.pdf_file.save(
                pdf_file.name,
                pdf_file,
                save=True
            )
            invoice.total_amount = order.total
            invoice.save()
        
        # Order-level transaction charge (sum of transaction_fee for this order)
        txn_charge_agg = order.transactions.filter(
            transaction_category='transaction_fee',
            status='success',
        ).aggregate(Sum('amount'))
        transaction_charge = txn_charge_agg['amount__sum']
        transaction_charge_str = str(transaction_charge) if transaction_charge is not None else None

        # Build items list
        items = []
        for item in order.items.all():
            product_image_url = None
            if item.product and item.product.image:
                try:
                    product_image_url = request.build_absolute_uri(item.product.image.url)
                except Exception:
                    pass
            item_data = {
                'id': item.id,
                'product_name': item.product.name if item.product else 'Unknown',
                'quantity': item.quantity,
                'price': str(item.price),
                'total': str(item.total),
                'product_image_url': product_image_url,
            }
            if item.product_variant:
                item_data['variant'] = {
                    'unit_name': item.product_variant.unit.name if item.product_variant.unit else None,
                    'unit_value': getattr(item.product_variant, 'unit_value', 1),
                }
            items.append(item_data)
        
        # Build vendor info
        vendor_info = None
        if order.user:
            vendor_info = {
                'name': order.user.name,
                'phone': order.user.phone,
                'address': order.user.address,
                'logo_url': request.build_absolute_uri(order.user.logo.url) if order.user.logo else None,
            }
        
        # Build response data
        response_data = {
            'invoice': {
                'id': invoice.id,
                'invoice_number': invoice.invoice_number,
                'generated_at': invoice.generated_at.isoformat(),
            },
            'order': {
                'id': order.id,
                'status': order.status,
                'payment_method': _get_order_payment_method(order),
                'total': str(order.total),
                'remarks': '',
                'customer_name': order.name,
                'customer_phone': order.phone or '',
                'customer_number': f'Order #{order.id}',
                'transaction_charge': transaction_charge_str,
                'created_at': order.created_at.isoformat(),
            },
            'items': items,
            'vendor': vendor_info,
            'pdf_url': request.build_absolute_uri(invoice.pdf_file.url) if invoice.pdf_file else None,
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def invoice_public_download(request, order_id, token):
    """
    Public endpoint to download invoice PDF without authentication.
    Token is verified using HMAC to ensure the request is valid.
    """
    # Verify token
    if not verify_invoice_token(order_id, token):
        return Response(
            {'error': 'Invalid or expired token'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        # Get order
        order = Order.objects.prefetch_related(
            'items__product', 
            'items__product_variant__unit'
        ).get(id=order_id)
        
        # Get or create invoice
        invoice, created = Invoice.objects.get_or_create(
            order=order,
            defaults={
                'invoice_number': f'INV-{order.id}-{datetime.now().strftime("%Y%m%d%H%M%S")}',
                'total_amount': order.total
            }
        )
        
        # Generate PDF if missing
        if not invoice.pdf_file or not invoice.pdf_file.name:
            pdf_file = generate_order_invoice(order)
            invoice.pdf_file.save(
                pdf_file.name,
                pdf_file,
                save=True
            )
            invoice.total_amount = order.total
            invoice.save()
        
        # Return PDF from memory so response is independent of storage/file handle lifecycle
        try:
            with invoice.pdf_file.open('rb') as f:
                pdf_bytes = f.read()
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="invoice_order_{order.id}.pdf"'
            return response
        except Exception as e:
            return Response(
                {'error': f'Failed to read PDF file: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
    except Order.DoesNotExist:
        return Response(
            {'error': 'Order not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
