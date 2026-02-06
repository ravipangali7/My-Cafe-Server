"""
PDF Generation Service for Order Invoices
Single-page layout: logo top-left, INVOICE top-right, customer block, items with image, summary with optional transaction charge.
"""
import base64
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


def _safe_hex_color(hex_str, fallback_rgb=(0.2, 0.2, 0.2)):
    """Return ReportLab color from hex, or fallback to avoid PDF generation crashes."""
    try:
        return colors.HexColor(hex_str)
    except Exception:
        return colors.Color(*fallback_rgb)


def _format_discount(discount_type, discount_value):
    """Format discount for display: percentage -> 'X%', flat -> '₹X.XX', else '—'."""
    if not discount_type or discount_value is None:
        return "—"
    try:
        val = float(discount_value)
    except (TypeError, ValueError):
        return "—"
    if discount_type == 'percentage':
        return f"{val:.0f}%" if val == int(val) else f"{val}%"
    if discount_type == 'flat':
        return f"₹{val:.2f}"
    return "—"


# Design colors (from reference image); defensive so invalid values do not crash PDF
LIGHT_BEIGE = _safe_hex_color('#F8F7F2', (0.973, 0.969, 0.949))
ACCENT = _safe_hex_color('#CC9999', (0.8, 0.6, 0.6))
FOOTER_GREEN = _safe_hex_color('#8C9C66', (0.55, 0.61, 0.4))
DARK_GRAY = _safe_hex_color('#333333', (0.2, 0.2, 0.2))
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

    invoice_date = order.created_at.strftime('%d/%m/%Y')
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

    # Header: logo | vendor name + phone | location (or placeholder)
    vendor_block = Paragraph(
        f"<b>{vendor_name}</b><br/>{vendor_phone or '—'}",
        body_style,
    )
    location_text = vendor_address.strip() if vendor_address else "—"
    location_para = Paragraph(location_text, body_style)
    header_table = Table(
        [[logo_table, vendor_block, location_para]],
        colWidths=[1.6 * inch, 3.2 * inch, 2.2 * inch],
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('LEFTPADDING', (1, 0), (1, -1), 12),
        ('RIGHTPADDING', (2, 0), (2, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.2 * inch))

    # --- Thick divider ---
    thick_divider = Table([[""]], colWidths=[7 * inch], rowHeights=[6])
    thick_divider.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DARK_GRAY),
        ('LINEABOVE', (0, 0), (-1, -1), 2, DARK_GRAY),
        ('LINEBELOW', (0, 0), (-1, -1), 2, DARK_GRAY),
    ]))
    elements.append(thick_divider)
    elements.append(Spacer(1, 0.15 * inch))

    # --- Invoice meta: Invoice No. left, Invoice Date right ---
    meta_left = Paragraph(f"<b>Invoice No.:</b> {order.id}", body_style)
    meta_right = Paragraph(f"<b>Invoice Date:</b> {invoice_date}", body_style)
    meta_table = Table(
        [[meta_left, meta_right]],
        colWidths=[3.5 * inch, 3.5 * inch],
    )
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (1, 0), (1, -1), 0),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 0.2 * inch))

    # --- Customer information: name left, phone right ---
    customer_left = Paragraph(f"<b>Customer name:</b> {order.name or '—'}", body_style)
    customer_right = Paragraph(f"<b>Customer phone:</b> {order.phone or '—'}", body_style)
    customer_table = Table(
        [[customer_left, customer_right]],
        colWidths=[3.5 * inch, 3.5 * inch],
    )
    customer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (1, 0), (1, -1), 0),
    ]))
    elements.append(customer_table)
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

    # --- Items table: IMAGE, ITEM NAME, QTY, PRICE, DISCOUNT, AMOUNT ---
    order_items = order.items.select_related('product', 'product_variant__unit').all()
    img_size = 0.55 * inch
    table_data = [['', '', 'QTY.', 'RATE', 'DISCOUNT', 'AMOUNT']]
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
        pv = item.product_variant
        discount_str = _format_discount(
            getattr(pv, 'discount_type', None),
            getattr(pv, 'discount_value', None),
        )
        table_data.append([
            img_flowable,
            Paragraph(f"{product_name}{variant_info}", body_style),
            Paragraph(str(item.quantity), body_style),
            Paragraph(f"₹{float(item.price):.2f}", body_style),
            Paragraph(discount_str, body_style),
            Paragraph(f"₹{float(item.total):.2f}", body_style),
        ])

    items_table = Table(
        table_data,
        colWidths=[0.7 * inch, 2.6 * inch, 0.5 * inch, 0.9 * inch, 0.9 * inch, 1.0 * inch],
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

    # --- Summary: Subtotal, Service charge (fixed Rs), Total (₹) ---
    total_amount = float(order.total)
    subtotal_amount = sum(float(i.total) for i in order_items)
    service_charge_val = float(transaction_charge_val) if transaction_charge_val is not None else 0
    summary_data = [
        [Paragraph("Subtotal", body_style), Paragraph(f"₹{subtotal_amount:.2f}", body_style)],
        [Paragraph("Service charge", body_style), Paragraph(f"₹{service_charge_val:.2f}", body_style)],
        [Paragraph("Total", body_bold_style), Paragraph(f"₹{total_amount:.2f}", body_bold_style)],
    ]
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

    # Build PDF with custom canvas (beige background + olive footer)
    doc.build(elements, canvasmaker=BeigeInvoiceCanvas)

    pdf = buffer.getvalue()
    buffer.close()
    if len(pdf) < 100:
        raise ValueError("Generated PDF is empty or invalid")
    filename = f'invoice_order_{order.id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    return ContentFile(pdf, name=filename)


def _image_from_base64(data, width_inch, height_inch):
    """Decode base64 image (raw or data URL) and return ReportLab Image flowable, or None."""
    if not data:
        return None
    raw = data
    if isinstance(data, str) and data.startswith('data:'):
        try:
            raw = data.split(',', 1)[1]
        except IndexError:
            return None
    try:
        buf = BytesIO(base64.b64decode(raw))
        return Image(buf, width=width_inch, height=height_inch)
    except Exception:
        return None


def generate_invoice_pdf_from_payload(payload):
    """
    Generate a PDF invoice from the same JSON payload the React public page uses.
    Layout and formatting match the React design: labels, ₹ currency, remarks, payment_method, date, variant.
    Optional: vendor.logo_base64, items[].product_image_base64 for embedding images; otherwise placeholder.
    Returns raw PDF bytes.
    """
    invoice = payload.get('invoice') or {}
    order = payload.get('order') or {}
    items = payload.get('items') or []
    vendor = payload.get('vendor') or {}

    # Computed values (React sends these so PDF matches exactly)
    subtotal_val = payload.get('subtotal')
    if subtotal_val is None:
        subtotal_val = sum(float(i.get('total', 0)) for i in items)
    tax_pct = payload.get('taxPercent', 0)
    tax_amount_val = payload.get('taxAmount', 0)
    transaction_charge_val = payload.get('transactionCharge', 0)
    if transaction_charge_val is None and order.get('transaction_charge') is not None:
        try:
            transaction_charge_val = float(order['transaction_charge'])
        except (TypeError, ValueError):
            transaction_charge_val = 0
    total_val = payload.get('total')
    if total_val is None:
        total_val = float(order.get('total', 0))
    order_date_str = payload.get('orderDate')
    invoice_date_str = payload.get('invoiceDate')
    if not order_date_str and order.get('created_at'):
        try:
            dt = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))
            order_date_str = dt.strftime('%m/%d/%Y')
        except Exception:
            order_date_str = str(order.get('created_at', ''))
    if not invoice_date_str and order.get('created_at'):
        try:
            dt = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00'))
            invoice_date_str = dt.strftime('%d/%m/%Y')
        except Exception:
            invoice_date_str = order_date_str or '—'

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

    order_id = order.get('id', '')
    vendor_name = vendor.get('name') or 'Vendor'
    vendor_phone = vendor.get('phone') or ''
    vendor_address = vendor.get('address') or ''
    customer_name = order.get('customer_name') or 'Customer'
    customer_phone = order.get('customer_phone') or ''

    # --- Header: logo left, vendor name/address/phone right (no Due Date) ---
    logo_flowable = None
    logo_b64 = vendor.get('logo_base64')
    if logo_b64:
        logo_flowable = _image_from_base64(logo_b64, 1.2 * inch, 1.2 * inch)
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

    # Header: logo | vendor name + phone | location (or placeholder)
    vendor_block = Paragraph(
        f"<b>{vendor_name}</b><br/>{vendor_phone or '—'}",
        body_style,
    )
    location_text = (vendor_address or "").strip() or "—"
    location_para = Paragraph(location_text, body_style)
    header_table = Table(
        [[logo_table, vendor_block, location_para]],
        colWidths=[1.6 * inch, 3.2 * inch, 2.2 * inch],
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('LEFTPADDING', (1, 0), (1, -1), 12),
        ('RIGHTPADDING', (2, 0), (2, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.2 * inch))

    # --- Thick divider ---
    thick_divider = Table([[""]], colWidths=[7 * inch], rowHeights=[6])
    thick_divider.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DARK_GRAY),
        ('LINEABOVE', (0, 0), (-1, -1), 2, DARK_GRAY),
        ('LINEBELOW', (0, 0), (-1, -1), 2, DARK_GRAY),
    ]))
    elements.append(thick_divider)
    elements.append(Spacer(1, 0.15 * inch))

    # --- Invoice meta: Invoice No. left, Invoice Date right ---
    meta_left = Paragraph(f"<b>Invoice No.:</b> {order_id}", body_style)
    meta_right = Paragraph(f"<b>Invoice Date:</b> {invoice_date_str or '—'}", body_style)
    meta_table = Table(
        [[meta_left, meta_right]],
        colWidths=[3.5 * inch, 3.5 * inch],
    )
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (1, 0), (1, -1), 0),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 0.2 * inch))

    # --- Customer information: name left, phone right ---
    customer_left = Paragraph(f"<b>Customer name:</b> {customer_name}", body_style)
    customer_right = Paragraph(f"<b>Customer phone:</b> {customer_phone or '—'}", body_style)
    customer_table = Table(
        [[customer_left, customer_right]],
        colWidths=[3.5 * inch, 3.5 * inch],
    )
    customer_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (0, -1), 0),
        ('RIGHTPADDING', (1, 0), (1, -1), 0),
    ]))
    elements.append(customer_table)
    elements.append(Spacer(1, 0.2 * inch))

    # --- Divider ---
    divider = Table([[""]], colWidths=[7 * inch], rowHeights=[3])
    divider.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ACCENT),
        ('LINEABOVE', (0, 0), (-1, -1), 0, ACCENT),
        ('LINEBELOW', (0, 0), (-1, -1), 0, ACCENT),
    ]))
    elements.append(divider)
    elements.append(Spacer(1, 0.15 * inch))

    # --- Items table: Image, Item Name, Qty, Price, Discount, Amount (₹) ---
    img_size = 0.55 * inch
    table_data = [['', '', 'QTY.', 'RATE', 'DISCOUNT', 'AMOUNT']]
    for item in items:
        product_name = item.get('product_name') or 'Unknown'
        variant = item.get('variant') or {}
        variant_str = ''
        if variant.get('unit_name'):
            uv = variant.get('unit_value')
            variant_str = f" ({uv} {variant['unit_name']})" if uv is not None else f" ({variant['unit_name']})"
        desc_text = f"{product_name}{variant_str}"

        img_flowable = Paragraph("—", body_style)
        img_b64 = item.get('product_image_base64')
        if img_b64:
            img_flowable = _image_from_base64(img_b64, img_size, img_size) or img_flowable

        price_val = float(item.get('price', 0))
        total_item = float(item.get('total', 0))
        discount_str = _format_discount(
            item.get('discount_type'),
            item.get('discount_value'),
        )
        table_data.append([
            img_flowable,
            Paragraph(desc_text, body_style),
            Paragraph(str(item.get('quantity', 0)), body_style),
            Paragraph(f"₹{price_val:.2f}", body_style),
            Paragraph(discount_str, body_style),
            Paragraph(f"₹{total_item:.2f}", body_style),
        ])

    items_table = Table(
        table_data,
        colWidths=[0.7 * inch, 2.6 * inch, 0.5 * inch, 0.9 * inch, 0.9 * inch, 1.0 * inch],
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

    # --- Summary: Subtotal, Service charge (fixed Rs), Total (₹) ---
    service_charge_val = float(transaction_charge_val) if transaction_charge_val is not None else 0
    summary_data = [
        [Paragraph("Subtotal", body_style), Paragraph(f"₹{float(subtotal_val):.2f}", body_style)],
        [Paragraph("Service charge", body_style), Paragraph(f"₹{service_charge_val:.2f}", body_style)],
        [Paragraph("Total", body_bold_style), Paragraph(f"₹{float(total_val):.2f}", body_bold_style)],
    ]
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

    doc.build(elements, canvasmaker=BeigeInvoiceCanvas)
    pdf = buffer.getvalue()
    buffer.close()
    if len(pdf) < 100:
        raise ValueError("Generated PDF is empty or invalid")
    return pdf
