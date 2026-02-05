"""
PDF Generation Service for Order Invoices
Single-page layout: logo top-left, INVOICE top-right, customer block, items with image, summary with optional transaction charge.
"""
import os
from io import BytesIO
from datetime import datetime
from django.db.models import Sum
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

    def _startPage(self):
        """Draw background and footer at the start of each page so they sit under content."""
        self.saveState()
        # Beige background
        self.setFillColor(LIGHT_BEIGE)
        self.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
        # Olive footer band
        self.setFillColor(FOOTER_GREEN)
        self.rect(0, 0, letter[0], self.footer_height, fill=1, stroke=0)
        self.restoreState()
        super()._startPage()

    def showPage(self):
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
        alignment=TA_RIGHT,
        fontName='Helvetica-Bold',
        leading=32,
    )
    invoice_num_style_right = ParagraphStyle(
        'InvoiceNumRight',
        parent=styles['Normal'],
        fontSize=8,
        textColor=DARK_GRAY,
        alignment=TA_RIGHT,
        fontName='Helvetica',
        leading=10,
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

    # Order-level transaction charge
    txn_charge_agg = order.transactions.filter(
        transaction_category='transaction_fee',
        status='success',
    ).aggregate(Sum('amount'))
    transaction_charge = txn_charge_agg.get('amount__sum')
    transaction_charge_val = float(transaction_charge) if transaction_charge is not None else None

    # --- Header: logo top-left, INVOICE top-right ---
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

    title_right = Paragraph("INVOICE", title_style)
    num_right = Paragraph(invoice_number, invoice_num_style_right)
    header_right = Table([[title_right], [num_right]], colWidths=[2.5 * inch])
    header_right.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
    ]))
    header_table = Table(
        [[logo_table, header_right]],
        colWidths=[1.6 * inch, 5.4 * inch],
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.25 * inch))

    # --- Customer information ---
    customer_para = Paragraph(
        f"<b>Customer:</b> {order.name or '—'}<br/><b>Customer number:</b> Order #{order.id}",
        body_style,
    )
    elements.append(customer_para)
    elements.append(Spacer(1, 0.2 * inch))

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

    # --- Items table: IMAGE, DESCRIPTION, QTY, PRICE, TOTAL ---
    order_items = order.items.select_related('product', 'product_variant__unit').all()
    img_size = 0.55 * inch
    table_data = [['IMAGE', 'DESCRIPTION', 'QTY', 'PRICE', 'TOTAL']]
    for item in order_items:
        product = item.product
        product_name = product.name if product else "Unknown Product"
        variant_info = ""
        if item.product_variant and item.product_variant.unit:
            variant_info = f" ({item.product_variant.unit.symbol})"
        # Product image or placeholder
        img_flowable = Paragraph("—", body_style)
        if product and product.image and os.path.exists(product.image.path):
            try:
                img = PILImage.open(product.image.path)
                img.thumbnail((80, 80), PILImage.Resampling.LANCZOS)
                img_buf = BytesIO()
                img.save(img_buf, format='PNG')
                img_buf.seek(0)
                img_flowable = Image(img_buf, width=img_size, height=img_size)
            except Exception:
                pass
        table_data.append([
            img_flowable,
            Paragraph(f"{product_name}{variant_info}", body_style),
            Paragraph(str(item.quantity), body_style),
            Paragraph(f"{float(item.price):.2f}", body_style),
            Paragraph(f"{float(item.total):.2f}", body_style),
        ])

    items_table = Table(
        table_data,
        colWidths=[0.7 * inch, 3.2 * inch, 0.7 * inch, 1.0 * inch, 1.1 * inch],
    )
    items_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('TEXTCOLOR', (0, 0), (-1, 0), DARK_GRAY),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('LINEABOVE', (0, 0), (-1, 0), 1.5, ACCENT),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, ACCENT),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, ACCENT),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 0.25 * inch))

    # --- Summary: Subtotal, Tax, Transaction charge (if any), Total ---
    total_amount = float(order.total)
    subtotal_amount = sum(float(i.total) for i in order_items)
    tax_pct = 0
    tax_amount = 0
    summary_data = [
        [Paragraph("Subtotal", body_style), Paragraph(f"{subtotal_amount:.2f}", body_style)],
        [Paragraph(f"Tax ({tax_pct}%)", body_style), Paragraph(f"{tax_amount:.2f}", body_style)],
    ]
    if transaction_charge_val is not None and transaction_charge_val > 0:
        summary_data.append([
            Paragraph("Transaction charge", body_style),
            Paragraph(f"{transaction_charge_val:.2f}", body_style),
        ])
    summary_data.append([
        Paragraph("Total", body_bold_style),
        Paragraph(f"{total_amount:.2f}", body_bold_style),
    ])
    summary_table = Table(summary_data, colWidths=[1.4 * inch, 1.2 * inch])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, -1), (1, -1), 10),
        ('FONTNAME', (0, -1), (1, -1), 'Helvetica-Bold'),
        ('LINEABOVE', (0, -1), (1, -1), 1, ACCENT),
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
