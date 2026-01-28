"""
PDF Generation Service for Order Invoices
"""
import os
from io import BytesIO
from decimal import Decimal
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.pdfgen import canvas
from PIL import Image as PILImage
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from ..models import Invoice
from .logo_service import generate_logo_image


def generate_order_invoice(order):
    """
    Generate a PDF invoice for an order matching the image design.
    Returns the PDF file as a ContentFile.
    """
    # Create a BytesIO buffer for the PDF
    buffer = BytesIO()
    
    # Create the PDF document with minimal margins
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.3*inch,
        leftMargin=0.3*inch,
        topMargin=0.3*inch,
        bottomMargin=0.3*inch
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define color constants
    DARK_BLUE = colors.HexColor('#1C455A')
    ORANGE = colors.HexColor('#FF8C00')
    WHITE = colors.white
    DARK_GRAY = colors.HexColor('#333333')
    LIGHT_GRAY = colors.HexColor('#e0e0e0')
    LIGHT_BG = colors.HexColor('#f5f5f5')
    
    # Define styles
    styles = getSampleStyleSheet()
    
    # White text style for left panel
    white_text_style = ParagraphStyle(
        'WhiteText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=WHITE,
        leading=14,
        fontName='Helvetica'
    )
    
    # Bold white text style for left panel headings
    white_bold_style = ParagraphStyle(
        'WhiteBold',
        parent=styles['Normal'],
        fontSize=11,
        textColor=WHITE,
        leading=14,
        fontName='Helvetica-Bold'
    )
    
    # Logo placeholder style
    logo_style = ParagraphStyle(
        'LogoStyle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=WHITE,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold',
        leading=28
    )
    
    # Dark gray text style for right panel
    dark_text_style = ParagraphStyle(
        'DarkText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=DARK_GRAY,
        leading=14,
        fontName='Helvetica'
    )
    
    # Orange title style
    orange_title_style = ParagraphStyle(
        'OrangeTitle',
        parent=styles['Heading1'],
        fontSize=36,
        textColor=ORANGE,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=42
    )
    
    # Invoice number style (small, left-aligned)
    invoice_num_style = ParagraphStyle(
        'InvoiceNum',
        parent=styles['Normal'],
        fontSize=9,
        textColor=DARK_GRAY,
        alignment=TA_LEFT,
        fontName='Helvetica',
        leading=12
    )
    
    # Date label style
    date_label_style = ParagraphStyle(
        'DateLabel',
        parent=styles['Normal'],
        fontSize=9,
        textColor=DARK_GRAY,
        fontName='Helvetica-Bold',
        leading=12
    )
    
    # Date value style
    date_value_style = ParagraphStyle(
        'DateValue',
        parent=styles['Normal'],
        fontSize=9,
        textColor=DARK_GRAY,
        fontName='Helvetica',
        leading=12
    )
    
    # Footer orange text style
    footer_orange_style = ParagraphStyle(
        'FooterOrange',
        parent=styles['Normal'],
        fontSize=11,
        textColor=ORANGE,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold',
        leading=14
    )
    
    # Footer heading style
    footer_heading_style = ParagraphStyle(
        'FooterHeading',
        parent=styles['Normal'],
        fontSize=10,
        textColor=DARK_GRAY,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold',
        leading=14
    )
    
    # Get vendor information
    vendor = order.user
    vendor_name = vendor.name if vendor else "Unknown Vendor"
    vendor_phone = vendor.phone if vendor else ""
    vendor_logo_path = None
    
    if vendor and vendor.logo:
        vendor_logo_path = vendor.logo.path
        if not os.path.exists(vendor_logo_path):
            vendor_logo_path = None
    
    # Get invoice number
    try:
        invoice = Invoice.objects.get(order=order)
        invoice_number = invoice.invoice_number
    except Invoice.DoesNotExist:
        invoice_number = f'INV-{order.id:03d}'
    
    # Format invoice date
    invoice_date = order.created_at.strftime('%B %d, %Y')
    
    # Build LEFT PANEL (Dark Blue)
    left_panel_elements = []
    
    # Logo area
    if vendor_logo_path:
        try:
            logo_img = PILImage.open(vendor_logo_path)
            logo_img.thumbnail((120, 120), PILImage.Resampling.LANCZOS)
            logo_buffer = BytesIO()
            logo_img.save(logo_buffer, format='PNG')
            logo_buffer.seek(0)
            logo = Image(logo_buffer, width=1.5*inch, height=1.5*inch)
            left_panel_elements.append(logo)
        except Exception:
            left_panel_elements.append(Paragraph("Your® LOGO", logo_style))
    else:
        # Auto-generated logo from vendor name
        try:
            logo_buffer = generate_logo_image(vendor_name, size=(120, 120))
            logo = Image(logo_buffer, width=1.5*inch, height=1.5*inch)
            left_panel_elements.append(logo)
        except Exception:
            left_panel_elements.append(Paragraph("Your® LOGO", logo_style))
    
    left_panel_elements.append(Spacer(1, 0.4*inch))
    
    # FROM section
    from_section = f"""
    <b>FROM</b><br/><br/>
    <b>{vendor_name}</b><br/>
    Phone: {vendor_phone}
    """
    left_panel_elements.append(Paragraph(from_section, white_text_style))
    left_panel_elements.append(Spacer(1, 0.5*inch))
    
    # TO section
    to_section = f"""
    <b>TO</b><br/><br/>
    <b>{order.name}</b><br/>
    {order.table_no}
    """
    left_panel_elements.append(Paragraph(to_section, white_text_style))
    
    # Create left panel table with dark blue background
    left_panel_table = Table([[left_panel_elements]], colWidths=[2*inch])
    left_panel_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DARK_BLUE),
        ('LEFTPADDING', (0, 0), (-1, -1), 20),
        ('RIGHTPADDING', (0, 0), (-1, -1), 20),
        ('TOPPADDING', (0, 0), (-1, -1), 30),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 30),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    # Build RIGHT PANEL (White)
    right_panel_elements = []
    
    # Large orange INVOICE title
    right_panel_elements.append(Paragraph("INVOICE", orange_title_style))
    right_panel_elements.append(Spacer(1, 0.3*inch))
    
    # Invoice date only (no due date)
    right_panel_elements.append(Paragraph("INVOICE DATE", date_label_style))
    right_panel_elements.append(Paragraph(invoice_date, date_value_style))
    right_panel_elements.append(Spacer(1, 0.1*inch))
    
    # Invoice number below invoice date
    invoice_num_text = f"INVOICE NO. {invoice_number}"
    right_panel_elements.append(Paragraph(invoice_num_text, invoice_num_style))
    right_panel_elements.append(Spacer(1, 0.4*inch))
    
    # Itemized table
    table_data = [['DESCRIPTION', 'QUANTITY', 'RATE', 'AMOUNT']]
    
    # Fetch order items
    order_items = order.items.select_related('product', 'product_variant__unit').all()
    
    for item in order_items:
        product = item.product
        product_name = product.name if product else "Unknown Product"
        quantity = item.quantity
        unit_price = float(item.price)
        subtotal = float(item.total)
        
        # Get variant info
        variant_info = ""
        if item.product_variant and item.product_variant.unit:
            variant_info = f" ({item.product_variant.unit.symbol})"
        
        table_data.append([
            Paragraph(f"{product_name}{variant_info}", dark_text_style),
            Paragraph(str(quantity), dark_text_style),
            Paragraph(f"{unit_price:.2f}", dark_text_style),
            Paragraph(f"{subtotal:.2f}", dark_text_style)
        ])
    
    # Create items table with orange header (adjusted widths to fit)
    items_table = Table(table_data, colWidths=[2.8*inch, 0.85*inch, 0.85*inch, 0.85*inch])
    items_table.setStyle(TableStyle([
        # Header row - orange background
        ('BACKGROUND', (0, 0), (-1, 0), ORANGE),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),  # DESCRIPTION left
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),  # QUANTITY center
        ('ALIGN', (2, 0), (2, 0), 'CENTER'),  # RATE center
        ('ALIGN', (3, 0), (3, 0), 'RIGHT'),  # AMOUNT right
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),  # DESCRIPTION left
        ('ALIGN', (1, 1), (1, -1), 'CENTER'),  # QUANTITY center
        ('ALIGN', (2, 1), (2, -1), 'CENTER'),  # RATE center
        ('ALIGN', (3, 1), (3, -1), 'RIGHT'),  # AMOUNT right
        ('TEXTCOLOR', (0, 1), (-1, -1), DARK_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 1), (-1, -1), 8),
        ('RIGHTPADDING', (0, 1), (-1, -1), 12),
        ('TOPPADDING', (0, 1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
    ]))
    
    right_panel_elements.append(items_table)
    right_panel_elements.append(Spacer(1, 0.4*inch))
    
    # Summary section
    total_amount = float(order.total)
    
    summary_data = [
        ['Subtotal:', f'{total_amount:.2f}'],
        ['GRAND TOTAL:', f'{total_amount:.2f}'],
    ]
    
    summary_table = Table(summary_data, colWidths=[3.5*inch, 1.2*inch])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (0, 0), 'Helvetica'),
        ('FONTNAME', (0, 1), (1, 1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (0, 0), 10),
        ('FONTSIZE', (0, 1), (1, 1), 12),
        ('TEXTCOLOR', (0, 0), (1, 0), DARK_GRAY),
        ('TEXTCOLOR', (0, 1), (1, 1), DARK_GRAY),
        ('LINEABOVE', (0, 1), (1, 1), 2, DARK_GRAY),
        ('TOPPADDING', (0, 1), (1, 1), 12),
        ('BOTTOMPADDING', (0, 1), (1, 1), 12),
        ('BACKGROUND', (0, 1), (1, 1), LIGHT_BG),
        ('RIGHTPADDING', (1, 0), (1, -1), 15),
    ]))
    
    right_panel_elements.append(summary_table)
    right_panel_elements.append(Spacer(1, 0.5*inch))
    
    # Footer
    footer_text = Paragraph("Thank you for our partnership!", footer_orange_style)
    right_panel_elements.append(footer_text)
    
    # Create right panel table
    right_panel_table = Table([[right_panel_elements]], colWidths=[5*inch])
    right_panel_table.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 20),
        ('RIGHTPADDING', (0, 0), (-1, -1), 35),
        ('TOPPADDING', (0, 0), (-1, -1), 30),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 30),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    # Create main two-column layout
    main_table = Table([[left_panel_table, right_panel_table]], colWidths=[2*inch, 5*inch])
    main_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    
    elements.append(main_table)
    
    # Build PDF
    doc.build(elements)
    
    # Get the value of the BytesIO buffer
    pdf = buffer.getvalue()
    buffer.close()
    
    # Create a ContentFile from the PDF
    filename = f'invoice_order_{order.id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    pdf_file = ContentFile(pdf, name=filename)
    
    return pdf_file
