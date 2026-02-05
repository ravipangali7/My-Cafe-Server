"""
PDF Generation Service for Order Invoices
Single-page layout matching reference design: beige background, accent dividers, olive footer.
"""
import os
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.pdfgen import canvas
from PIL import Image as PILImage
from django.core.files.base import ContentFile
from ..models import Invoice
from .logo_service import generate_logo_image


# Design colors (from reference image)
LIGHT_BEIGE = colors.HexColor('#F8F7F2')
ACCENT = colors.HexColor('#CC9999')
FOOTER_GREEN = colors.HexColor('#8C9C66')
DARK_GRAY = colors.HexColor('#333333')
WHITE = colors.white


class BeigeInvoiceCanvas(canvas.Canvas):
    """Canvas that draws beige page background and olive footer band."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.footer_height = 0.28 * inch

    def showPage(self):
        self.saveState()
        # Beige background
        self.setFillColor(LIGHT_BEIGE)
        self.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
        # Olive footer band
        self.setFillColor(FOOTER_GREEN)
        self.rect(0, 0, letter[0], self.footer_height, fill=1, stroke=0)
        self.restoreState()
        super().showPage()


def generate_order_invoice(order):
    """
    Generate a PDF invoice for an order matching the image design.
    Single-page, centered layout: logo, title, FROM/TO, table, summary, terms/payment, olive footer.
    Returns the PDF file as a ContentFile.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.5 * inch,
    )
    elements = []
    styles = getSampleStyleSheet()

    # Styles
    title_style = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Normal'],
        fontSize=28,
        textColor=DARK_GRAY,
        alignment=TA_CENTER,
        fontName='Times-Bold',
        leading=32,
    )
    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Normal'],
        fontSize=8,
        textColor=DARK_GRAY,
        fontName='Helvetica-Bold',
        leading=10,
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=9,
        textColor=DARK_GRAY,
        leading=12,
        fontName='Helvetica',
    )
    body_bold_style = ParagraphStyle(
        'BodyBold',
        parent=styles['Normal'],
        fontSize=9,
        textColor=DARK_GRAY,
        leading=12,
        fontName='Helvetica-Bold',
    )
    invoice_num_style = ParagraphStyle(
        'InvoiceNum',
        parent=styles['Normal'],
        fontSize=8,
        textColor=DARK_GRAY,
        alignment=TA_CENTER,
        fontName='Helvetica',
        leading=10,
    )
    banner_text_style = ParagraphStyle(
        'BannerText',
        parent=styles['Normal'],
        fontSize=10,
        textColor=WHITE,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=12,
    )

    vendor = order.user
    vendor_name = vendor.name if vendor else "Unknown Vendor"
    vendor_phone = vendor.phone if vendor else ""
    vendor_address = getattr(vendor, 'address', None) or ""
    vendor_logo_path = None
    if vendor and vendor.logo:
        vendor_logo_path = vendor.logo.path
        if not os.path.exists(vendor_logo_path):
            vendor_logo_path = None

    try:
        inv = Invoice.objects.get(order=order)
        invoice_number = inv.invoice_number
    except Invoice.DoesNotExist:
        invoice_number = f'INV-{order.id:03d}'

    invoice_date = order.created_at.strftime('%B %d, %Y')
    order_date_short = order.created_at.strftime('%m/%d/%Y')

    # --- Logo (centered) ---
    logo_flowable = None
    if vendor_logo_path:
        try:
            logo_img = PILImage.open(vendor_logo_path)
            logo_img.thumbnail((120, 120), PILImage.Resampling.LANCZOS)
            logo_buf = BytesIO()
            logo_img.save(logo_buf, format='PNG')
            logo_buf.seek(0)
            logo_flowable = Image(logo_buf, width=1.2 * inch, height=1.2 * inch)
        except Exception:
            pass
    if logo_flowable is None:
        try:
            logo_buf = generate_logo_image(vendor_name, size=(120, 120))
            logo_buf.seek(0)
            logo_flowable = Image(logo_buf, width=1.2 * inch, height=1.2 * inch)
        except Exception:
            logo_flowable = Paragraph("LOGO", body_bold_style)

    # Logo in a centered cell with accent border effect (table with padding acts as "ring")
    logo_table = Table(
        [[logo_flowable]],
        colWidths=[1.4 * inch],
        rowHeights=[1.4 * inch],
    )
    logo_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 2, ACCENT),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BEIGE),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(Table([[logo_table]], colWidths=[7 * inch]))
    elements[-1].setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))

    # Vendor name banner (optional strip in accent)
    banner_para = Paragraph(vendor_name.upper()[:40], banner_text_style)
    banner_tbl = Table([[banner_para]], colWidths=[2 * inch])
    banner_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ACCENT),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    wrap_banner = Table([[banner_tbl]], colWidths=[7 * inch])
    wrap_banner.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    elements.append(wrap_banner)
    elements.append(Spacer(1, 0.15 * inch))

    # --- Invoice title ---
    elements.append(Paragraph("Invoice", title_style))
    elements.append(Paragraph(invoice_number, invoice_num_style))
    elements.append(Spacer(1, 0.35 * inch))

    # --- INVOICE FROM | INVOICE TO ---
    from_para = Paragraph(
        f"<b>INVOICE FROM</b><br/><br/><b>{vendor_name}</b><br/>{vendor_phone or '—'}<br/>{vendor_address or '—'}",
        body_style,
    )
    to_para = Paragraph(
        f"<b>INVOICE TO</b><br/><br/><b>{order.name or '—'}</b><br/>{order.phone or '—'}<br/>{order.table_no or '—'}",
        body_style,
    )
    from_to_table = Table(
        [[from_para, to_para]],
        colWidths=[3.5 * inch, 3.5 * inch],
    )
    from_to_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (1, 0), (1, -1), 0),
    ]))
    elements.append(from_to_table)
    elements.append(Spacer(1, 0.2 * inch))

    # --- Divider (accent line) ---
    divider = Table([[""]], colWidths=[7 * inch], rowHeights=[3])
    divider.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ACCENT),
        ('LINEABOVE', (0, 0), (-1, -1), 0, ACCENT),
        ('LINEBELOW', (0, 0), (-1, -1), 0, ACCENT),
    ]))
    elements.append(divider)
    elements.append(Spacer(1, 0.15 * inch))

    # --- Items table: DESCRIPTION, QTY, PRICE, TOTAL ---
    order_items = order.items.select_related('product', 'product_variant__unit').all()
    table_data = [['DESCRIPTION', 'QTY', 'PRICE', 'TOTAL']]
    for item in order_items:
        product = item.product
        product_name = product.name if product else "Unknown Product"
        variant_info = ""
        if item.product_variant and item.product_variant.unit:
            variant_info = f" ({item.product_variant.unit.symbol})"
        table_data.append([
            Paragraph(f"{product_name}{variant_info}", body_style),
            Paragraph(str(item.quantity), body_style),
            Paragraph(f"{float(item.price):.2f}", body_style),
            Paragraph(f"{float(item.total):.2f}", body_style),
        ])

    items_table = Table(
        table_data,
        colWidths=[3.8 * inch, 0.9 * inch, 1.1 * inch, 1.2 * inch],
    )
    items_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('TEXTCOLOR', (0, 0), (-1, 0), DARK_GRAY),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('LINEABOVE', (0, 0), (-1, 0), 1.5, ACCENT),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, ACCENT),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, ACCENT),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 0.25 * inch))

    # --- Summary: Subtotal, Tax, Total ---
    total_amount = float(order.total)
    subtotal_amount = sum(float(i.total) for i in order_items)
    tax_pct = 0
    tax_amount = 0
    summary_data = [
        [Paragraph("Subtotal", body_style), Paragraph(f"{subtotal_amount:.2f}", body_style)],
        [Paragraph(f"Tax ({tax_pct}%)", body_style), Paragraph(f"{tax_amount:.2f}", body_style)],
        [Paragraph("Total", body_bold_style), Paragraph(f"{total_amount:.2f}", body_bold_style)],
    ]
    summary_table = Table(summary_data, colWidths=[1.2 * inch, 1.2 * inch])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 2), (1, 2), 10),
        ('LINEABOVE', (0, 2), (1, 2), 1, ACCENT),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    summary_wrapper = Table([[summary_table]], colWidths=[7 * inch])
    summary_wrapper.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'RIGHT')]))
    elements.append(summary_wrapper)
    elements.append(Spacer(1, 0.3 * inch))

    # --- TERMS & CONDITIONS | PAYMENT METHOD ---
    terms_text = "Thank you for your order."
    txn = order.transactions.filter(status='success').first()
    if txn and getattr(txn, 'ug_order_id', None):
        payment_method = "Online"
    elif txn and getattr(txn, 'vpa', None) and txn.vpa:
        payment_method = "UPI"
    elif txn:
        payment_method = "Other"
    else:
        payment_method = "Pending"

    terms_para = Paragraph(
        f"<b>TERMS &amp; CONDITIONS</b><br/><br/>{terms_text}",
        body_style,
    )
    payment_para = Paragraph(
        f"<b>PAYMENT METHOD</b><br/><br/>"
        f"Payment: {payment_method or '—'}<br/>Date: {order_date_short}",
        body_style,
    )
    terms_payment_table = Table(
        [[terms_para, payment_para]],
        colWidths=[3.5 * inch, 3.5 * inch],
    )
    terms_payment_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (1, 0), (1, -1), 20),
    ]))
    elements.append(terms_payment_table)
    elements.append(Spacer(1, 0.4 * inch))

    # Build PDF with custom canvas (beige background + olive footer)
    doc.build(elements, canvasmaker=BeigeInvoiceCanvas)

    pdf = buffer.getvalue()
    buffer.close()
    filename = f'invoice_order_{order.id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    return ContentFile(pdf, name=filename)
