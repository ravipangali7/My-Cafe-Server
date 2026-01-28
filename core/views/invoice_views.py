"""
Invoice views for generating and downloading PDF bills
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse, FileResponse
from django.core.files.base import ContentFile
from datetime import datetime
from ..models import Order, Invoice
from ..services.pdf_service import generate_order_invoice


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
        
        # Return PDF file as response (storage-agnostic: works with local and remote storage)
        try:
            file_handle = invoice.pdf_file.open('rb')
            response = FileResponse(
                file_handle,
                content_type='application/pdf'
            )
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
