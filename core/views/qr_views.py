from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import FileResponse, HttpResponse
from ..models import User
from ..serializers import UserSerializer
from ..services.qr_card_service import generate_qr_card_png, generate_qr_card_pdf


@api_view(['GET'])
def qr_generate(request, vendor_id):
    """Generate QR code data for a vendor"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Get vendor
        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions - superusers can generate for any vendor, others only for themselves
        if not request.user.is_superuser and vendor != request.user:
            return Response(
                {'error': 'You do not have permission to generate QR for this vendor'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Generate menu URL
        menu_url = f"{request.scheme}://{request.get_host()}/menu/{vendor.phone}"
        
        # Get vendor data
        serializer = UserSerializer(vendor, context={'request': request})
        
        return Response({
            'vendor': serializer.data,
            'menu_url': menu_url,
            'qr_data': {
                'value': menu_url,
                'size': 256,
                'level': 'H'
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def qr_download_pdf(request, vendor_id):
    """Generate QR code PDF (returns data for frontend PDF generation)"""
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        # Get vendor
        try:
            vendor = User.objects.get(id=vendor_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'Vendor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check permissions
        if not request.user.is_superuser and vendor != request.user:
            return Response(
                {'error': 'You do not have permission to generate QR for this vendor'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Generate menu URL
        menu_url = f"{request.scheme}://{request.get_host()}/menu/{vendor.phone}"
        
        # Get vendor data
        serializer = UserSerializer(vendor, context={'request': request})
        
        # Return data for frontend PDF generation
        # Frontend will use jspdf to generate the actual PDF
        return Response({
            'vendor': serializer.data,
            'menu_url': menu_url,
            'qr_data': {
                'value': menu_url,
                'size': 256,
                'level': 'H'
            },
            'pdf_data': {
                'title': f'QR Code - {vendor.name}',
                'my_cafe_logo_url': None,  # Frontend will handle logo
                'vendor_logo_url': serializer.data.get('logo_url'),
                'vendor_name': vendor.name,
                'qr_value': menu_url
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def qr_card_download_png(request, vendor_phone):
    """Download QR card as PNG. Public endpoint (by vendor_phone)."""
    vendor = User.objects.filter(phone=vendor_phone, is_active=True).first()
    if not vendor:
        return Response(
            {'error': 'Vendor not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    menu_url = f"{request.scheme}://{request.get_host()}/menu/{vendor.phone}"
    buffer = generate_qr_card_png(vendor, menu_url)
    filename = f"qr-code-{vendor.phone}.png"
    response = HttpResponse(buffer.getvalue(), content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@api_view(['GET'])
def qr_card_download_pdf(request, vendor_phone):
    """Download QR card as PDF. Public endpoint (by vendor_phone)."""
    vendor = User.objects.filter(phone=vendor_phone, is_active=True).first()
    if not vendor:
        return Response(
            {'error': 'Vendor not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    menu_url = f"{request.scheme}://{request.get_host()}/menu/{vendor.phone}"
    buffer = generate_qr_card_pdf(vendor, menu_url)
    filename = f"qr-code-{vendor.phone}.pdf"
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
