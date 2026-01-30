"""
Generate QR card as PNG or PDF. Design must match React MenuQRCode.tsx 100%.
Uses qr_card_constants for layout and React-identical get_initials/color_from_name.
"""
from io import BytesIO
import os

import qrcode
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas

from .qr_card_constants import (
    CARD_BG,
    CARD_BORDER_RADIUS,
    CARD_PADDING_TOP_BOTTOM,
    CARD_WIDTH,
    FOOTER_FONT_SIZE,
    FOOTER_MARGIN_TOP,
    GOLD,
    LOGO_BORDER_WIDTH,
    LOGO_MARGIN_BOTTOM,
    LOGO_SIZE,
    QR_CONTAINER_BORDER_WIDTH,
    QR_CONTAINER_PADDING,
    QR_CONTAINER_RADIUS,
    QR_FG,
    QR_BG,
    QR_MODULE_SIZE,
    SCAN_ORDER_FONT_SIZE,
    SCAN_ORDER_MARGIN_BOTTOM,
    SUBTITLE_FONT_SIZE,
    SUBTITLE_MARGIN_BOTTOM,
    TITLE_FONT_SIZE,
    TITLE_MARGIN_BOTTOM,
    color_from_name,
    get_initials,
    hex_to_rgb,
)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load sans-serif font; fallback for Windows/Linux."""
    names = [
        ("DejaVuSans-Bold.ttf", "DejaVu Sans Bold"),
        ("arial.ttf", "Arial"),
        ("Arial.ttf", "Arial"),
    ]
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in paths:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    for name, _ in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _make_logo_circle(vendor) -> Image.Image:
    """72x72 logo circle: vendor image (cropped to circle) or initials on color_from_name. Gold border 3px."""
    size = LOGO_SIZE
    gold_rgb = hex_to_rgb(GOLD)
    black_rgb = hex_to_rgb(CARD_BG)

    out = None
    logo_path = getattr(vendor.logo, "path", None) if getattr(vendor, "logo", None) else None
    if logo_path and os.path.isfile(logo_path):
        try:
            img = Image.open(logo_path).convert("RGB")
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (size, size), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, size - 1, size - 1), fill=255)
            out = Image.new("RGB", (size, size), black_rgb)
            out.paste(img, (0, 0), mask)
        except Exception:
            out = None
    if out is None:
        # Initials on color_from_name
        bg_hex = color_from_name(vendor.name if getattr(vendor, "name", None) else "")
        bg_rgb = hex_to_rgb(bg_hex)
        out = Image.new("RGB", (size, size), black_rgb)
        draw = ImageDraw.Draw(out)
        draw.ellipse((0, 0, size - 1, size - 1), fill=tuple(bg_rgb), outline=None)
        initials = get_initials(getattr(vendor, "name", "") or "")
        font = _load_font(24, bold=True)
        try:
            bbox = draw.textbbox((0, 0), initials, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            x = (size - tw) // 2 - bbox[0]
            y = (size - th) // 2 - bbox[1]
        except (TypeError, AttributeError):
            x = (size - 24) // 2
            y = (size - 24) // 2
        draw.text((x, y), initials, fill=(255, 255, 255), font=font)

    # Gold ring 3px: paste logo then draw ring on top
    ring_size = size + LOGO_BORDER_WIDTH * 2
    final = Image.new("RGB", (ring_size, ring_size), black_rgb)
    final.paste(out, (LOGO_BORDER_WIDTH, LOGO_BORDER_WIDTH))
    draw_final = ImageDraw.Draw(final)
    draw_final.ellipse((0, 0, ring_size - 1, ring_size - 1), outline=gold_rgb, width=LOGO_BORDER_WIDTH)
    return final


def _make_qr_image(menu_url: str) -> Image.Image:
    """200x200 QR code, level H, black on white."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=0,
    )
    qr.add_data(menu_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=QR_FG, back_color=QR_BG)
    img = img.convert("RGB")
    # Resize to exact 200x200
    if img.size != (QR_MODULE_SIZE, QR_MODULE_SIZE):
        img = img.resize((QR_MODULE_SIZE, QR_MODULE_SIZE), Image.Resampling.NEAREST)
    return img


def _build_card_image_impl(vendor, menu_url: str) -> Image.Image:
    """Internal: build card PIL Image."""
    padding_tb = CARD_PADDING_TOP_BOTTOM
    black_rgb = hex_to_rgb(CARD_BG)
    gold_rgb = hex_to_rgb(GOLD)
    white_rgb = (255, 255, 255)

    logo_block = LOGO_SIZE + LOGO_BORDER_WIDTH * 2
    title_h = TITLE_FONT_SIZE + 4
    subtitle_h = SUBTITLE_FONT_SIZE + 4
    scan_order_h = SCAN_ORDER_FONT_SIZE + 4
    qr_inner = QR_MODULE_SIZE
    qr_block_h = QR_CONTAINER_PADDING * 2 + qr_inner + QR_CONTAINER_BORDER_WIDTH * 2
    footer_h = FOOTER_FONT_SIZE + 4

    card_height = (
        padding_tb
        + logo_block
        + LOGO_MARGIN_BOTTOM
        + title_h
        + TITLE_MARGIN_BOTTOM
        + subtitle_h
        + SUBTITLE_MARGIN_BOTTOM
        + scan_order_h
        + SCAN_ORDER_MARGIN_BOTTOM
        + qr_block_h
        + FOOTER_MARGIN_TOP
        + footer_h
        + padding_tb
    )

    img = Image.new("RGB", (CARD_WIDTH, card_height), black_rgb)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        (0, 0, CARD_WIDTH - 1, card_height - 1),
        radius=CARD_BORDER_RADIUS,
        fill=black_rgb,
        outline=None,
    )

    y = padding_tb
    logo_img = _make_logo_circle(vendor)
    logo_x = (CARD_WIDTH - logo_img.width) // 2
    img.paste(logo_img, (logo_x, y))
    y += logo_img.height + LOGO_MARGIN_BOTTOM

    title_font = _load_font(TITLE_FONT_SIZE, bold=True)
    title_text = (getattr(vendor, "name", None) or "My Cafe").upper()
    try:
        bbox = draw.textbbox((0, 0), title_text, font=title_font)
        tw = bbox[2] - bbox[0]
    except (TypeError, AttributeError):
        tw = len(title_text) * 14
    title_x = (CARD_WIDTH - tw) // 2
    draw.text((title_x, y), title_text, fill=white_rgb, font=title_font)
    y += title_h + TITLE_MARGIN_BOTTOM

    sub_font = _load_font(SUBTITLE_FONT_SIZE)
    sub_text = "MENU QR CODE"
    try:
        bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
        tw = bbox[2] - bbox[0]
    except (TypeError, AttributeError):
        tw = len(sub_text) * 6
    sub_x = (CARD_WIDTH - tw) // 2
    draw.text((sub_x, y), sub_text, fill=(255, 255, 255), font=sub_font)
    y += subtitle_h + SUBTITLE_MARGIN_BOTTOM

    # Scan & Order Now - call to action text in gold
    scan_order_font = _load_font(SCAN_ORDER_FONT_SIZE, bold=True)
    scan_order_text = "Scan & Order Now"
    try:
        bbox = draw.textbbox((0, 0), scan_order_text, font=scan_order_font)
        tw = bbox[2] - bbox[0]
    except (TypeError, AttributeError):
        tw = len(scan_order_text) * 10
    scan_order_x = (CARD_WIDTH - tw) // 2
    draw.text((scan_order_x, y), scan_order_text, fill=gold_rgb, font=scan_order_font)
    y += scan_order_h + SCAN_ORDER_MARGIN_BOTTOM

    qr_container_w = QR_CONTAINER_PADDING * 2 + QR_MODULE_SIZE + QR_CONTAINER_BORDER_WIDTH * 2
    qr_container_h = qr_block_h
    qr_left = (CARD_WIDTH - qr_container_w) // 2
    qr_top = y
    draw.rounded_rectangle(
        (qr_left, qr_top, qr_left + qr_container_w - 1, qr_top + qr_container_h - 1),
        radius=QR_CONTAINER_RADIUS,
        fill=(255, 255, 255),
        outline=gold_rgb,
        width=QR_CONTAINER_BORDER_WIDTH,
    )
    qr_img = _make_qr_image(menu_url)
    qr_paste_x = qr_left + QR_CONTAINER_BORDER_WIDTH + QR_CONTAINER_PADDING
    qr_paste_y = qr_top + QR_CONTAINER_BORDER_WIDTH + QR_CONTAINER_PADDING
    img.paste(qr_img, (qr_paste_x, qr_paste_y))
    y += qr_block_h + FOOTER_MARGIN_TOP

    footer_font = _load_font(FOOTER_FONT_SIZE)
    vendor_name = getattr(vendor, "name", None) or "My Cafe"
    footer_text = f"© 2025 {vendor_name} | All Rights Reserved"
    try:
        bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
        tw = bbox[2] - bbox[0]
    except (TypeError, AttributeError):
        tw = len(footer_text) * 6
    footer_x = (CARD_WIDTH - tw) // 2
    draw.text((footer_x, y), footer_text, fill=(179, 179, 179), font=footer_font)

    return img


def generate_qr_card_png(vendor, menu_url: str) -> BytesIO:
    """Generate QR card as PNG bytes. Returns BytesIO."""
    img = _build_card_image_impl(vendor, menu_url)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def generate_qr_card_pdf(vendor, menu_url: str) -> BytesIO:
    """Generate QR card as single-page PDF. Card image embedded (same as PNG). Returns BytesIO."""
    img = _build_card_image_impl(vendor, menu_url)
    img_buffer = BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    pdf_buffer = BytesIO()
    page_w, page_h = A4
    c = pdf_canvas.Canvas(pdf_buffer, pagesize=A4)
    margin_mm_val = 20
    card_w_pt = CARD_WIDTH * 0.75
    card_h_pt = img.height * 0.75
    max_w = page_w - margin_mm_val * 2 * mm
    max_h = page_h - margin_mm_val * 2 * mm
    scale = min(max_w / card_w_pt, max_h / card_h_pt, 1.0)
    draw_w = card_w_pt * scale
    draw_h = card_h_pt * scale
    x = (page_w - draw_w) / 2
    y = page_h - draw_h - margin_mm_val * mm
    c.drawImage(
        ImageReader(img_buffer),
        x, y,
        width=draw_w,
        height=draw_h,
        preserveAspectRatio=True,
    )
    c.save()
    pdf_buffer.seek(0)
    return pdf_buffer
