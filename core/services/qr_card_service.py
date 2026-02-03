"""
Generate QR card as PNG or PDF. Design must match React MenuQRCode.tsx 100%.
Uses qr_card_constants for layout and React-identical get_initials/color_from_name.
Print output: 4" x 6" at 300 DPI (1200 x 1800 px) with margins for scannability.
"""
from io import BytesIO
import os

import qrcode
from PIL import Image, ImageDraw, ImageFont
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
    PRINT_CONTENT_H,
    PRINT_CONTENT_W,
    PRINT_HEIGHT_PX,
    PRINT_MARGIN_PX,
    PRINT_WIDTH_PX,
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


def _scale(design_val: int, scale: float) -> int:
    """Scale a design dimension by scale factor (design width 384 -> target width)."""
    return max(1, round(design_val * scale))


def _make_logo_circle(vendor, logo_size: int, logo_border_width: int) -> Image.Image:
    """Logo circle: vendor image (cropped to circle) or initials on color_from_name. Gold border."""
    size = logo_size
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
        font_size = max(12, _scale(24, size / LOGO_SIZE))
        font = _load_font(font_size, bold=True)
        try:
            bbox = draw.textbbox((0, 0), initials, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            x = (size - tw) // 2 - bbox[0]
            y = (size - th) // 2 - bbox[1]
        except (TypeError, AttributeError):
            x = (size - font_size) // 2
            y = (size - font_size) // 2
        draw.text((x, y), initials, fill=(255, 255, 255), font=font)

    # Gold ring: paste logo then draw ring on top
    ring_size = size + logo_border_width * 2
    final = Image.new("RGB", (ring_size, ring_size), black_rgb)
    final.paste(out, (logo_border_width, logo_border_width))
    draw_final = ImageDraw.Draw(final)
    draw_final.ellipse((0, 0, ring_size - 1, ring_size - 1), outline=gold_rgb, width=logo_border_width)
    return final


def _make_qr_image(menu_url: str, qr_module_size: int) -> Image.Image:
    """QR code at given module size (px), level H, black on white."""
    # box_size so that output is roughly qr_module_size; qrcode default ~21 modules for version 1
    box_size = max(1, qr_module_size // 21)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=0,
    )
    qr.add_data(menu_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=QR_FG, back_color=QR_BG)
    img = img.convert("RGB")
    if img.size != (qr_module_size, qr_module_size):
        img = img.resize((qr_module_size, qr_module_size), Image.Resampling.NEAREST)
    return img


def _build_card_image_impl(vendor, menu_url: str, card_width_px: int | None = None) -> Image.Image:
    """Internal: build card PIL Image at given width (default CARD_WIDTH). Scaled for print."""
    if card_width_px is None:
        card_width_px = CARD_WIDTH
    scale = card_width_px / CARD_WIDTH

    padding_tb = _scale(CARD_PADDING_TOP_BOTTOM, scale)
    black_rgb = hex_to_rgb(CARD_BG)
    gold_rgb = hex_to_rgb(GOLD)
    white_rgb = (255, 255, 255)

    logo_size = _scale(LOGO_SIZE, scale)
    logo_border_width = _scale(LOGO_BORDER_WIDTH, scale)
    logo_block = logo_size + logo_border_width * 2
    title_font_size = _scale(TITLE_FONT_SIZE, scale)
    subtitle_font_size = _scale(SUBTITLE_FONT_SIZE, scale)
    scan_order_font_size = _scale(SCAN_ORDER_FONT_SIZE, scale)
    footer_font_size = _scale(FOOTER_FONT_SIZE, scale)
    title_h = title_font_size + 4
    subtitle_h = subtitle_font_size + 4
    scan_order_h = scan_order_font_size + 4
    qr_module_size = _scale(QR_MODULE_SIZE, scale)
    qr_container_padding = _scale(QR_CONTAINER_PADDING, scale)
    qr_container_border_width = _scale(QR_CONTAINER_BORDER_WIDTH, scale)
    qr_block_h = qr_container_padding * 2 + qr_module_size + qr_container_border_width * 2
    footer_h = footer_font_size + 4

    logo_mb = _scale(LOGO_MARGIN_BOTTOM, scale)
    title_mb = _scale(TITLE_MARGIN_BOTTOM, scale)
    subtitle_mb = _scale(SUBTITLE_MARGIN_BOTTOM, scale)
    scan_order_mb = _scale(SCAN_ORDER_MARGIN_BOTTOM, scale)
    footer_mt = _scale(FOOTER_MARGIN_TOP, scale)
    card_border_radius = _scale(CARD_BORDER_RADIUS, scale)
    qr_container_radius = _scale(QR_CONTAINER_RADIUS, scale)

    card_height = (
        padding_tb
        + logo_block
        + logo_mb
        + title_h
        + title_mb
        + subtitle_h
        + subtitle_mb
        + scan_order_h
        + scan_order_mb
        + qr_block_h
        + footer_mt
        + footer_h
        + padding_tb
    )

    img = Image.new("RGB", (card_width_px, card_height), black_rgb)
    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        (0, 0, card_width_px - 1, card_height - 1),
        radius=card_border_radius,
        fill=black_rgb,
        outline=None,
    )

    y = padding_tb
    logo_img = _make_logo_circle(vendor, logo_size, logo_border_width)
    logo_x = (card_width_px - logo_img.width) // 2
    img.paste(logo_img, (logo_x, y))
    y += logo_img.height + logo_mb

    title_font = _load_font(title_font_size, bold=True)
    title_text = (getattr(vendor, "name", None) or "My Cafe").upper()
    try:
        bbox = draw.textbbox((0, 0), title_text, font=title_font)
        tw = bbox[2] - bbox[0]
    except (TypeError, AttributeError):
        tw = len(title_text) * 14
    title_x = (card_width_px - tw) // 2
    draw.text((title_x, y), title_text, fill=white_rgb, font=title_font)
    y += title_h + title_mb

    sub_font = _load_font(subtitle_font_size)
    sub_text = "MENU QR CODE"
    try:
        bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
        tw = bbox[2] - bbox[0]
    except (TypeError, AttributeError):
        tw = len(sub_text) * 6
    sub_x = (card_width_px - tw) // 2
    draw.text((sub_x, y), sub_text, fill=(255, 255, 255), font=sub_font)
    y += subtitle_h + subtitle_mb

    scan_order_font = _load_font(scan_order_font_size, bold=True)
    scan_order_text = "Scan & Order Now"
    try:
        bbox = draw.textbbox((0, 0), scan_order_text, font=scan_order_font)
        tw = bbox[2] - bbox[0]
    except (TypeError, AttributeError):
        tw = len(scan_order_text) * 10
    scan_order_x = (card_width_px - tw) // 2
    draw.text((scan_order_x, y), scan_order_text, fill=gold_rgb, font=scan_order_font)
    y += scan_order_h + scan_order_mb

    qr_container_w = qr_container_padding * 2 + qr_module_size + qr_container_border_width * 2
    qr_container_h = qr_block_h
    qr_left = (card_width_px - qr_container_w) // 2
    qr_top = y
    draw.rounded_rectangle(
        (qr_left, qr_top, qr_left + qr_container_w - 1, qr_top + qr_container_h - 1),
        radius=qr_container_radius,
        fill=(255, 255, 255),
        outline=gold_rgb,
        width=qr_container_border_width,
    )
    qr_img = _make_qr_image(menu_url, qr_module_size)
    qr_paste_x = qr_left + qr_container_border_width + qr_container_padding
    qr_paste_y = qr_top + qr_container_border_width + qr_container_padding
    img.paste(qr_img, (qr_paste_x, qr_paste_y))
    y += qr_block_h + footer_mt

    footer_font = _load_font(footer_font_size)
    vendor_name = getattr(vendor, "name", None) or "My Cafe"
    footer_text = f"© 2025 {vendor_name} | All Rights Reserved"
    try:
        bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
        tw = bbox[2] - bbox[0]
    except (TypeError, AttributeError):
        tw = len(footer_text) * 6
    footer_x = (card_width_px - tw) // 2
    draw.text((footer_x, y), footer_text, fill=(179, 179, 179), font=footer_font)

    return img


def _build_print_image(vendor, menu_url: str) -> Image.Image:
    """Build 4" x 6" print image at 300 DPI: card at PRINT_CONTENT_W width, centered on PRINT_WIDTH_PX x PRINT_HEIGHT_PX with margins."""
    card_img = _build_card_image_impl(vendor, menu_url, card_width_px=PRINT_CONTENT_W)
    card_w, card_h = card_img.size
    # Canvas: 1200 x 1800, margins 75 px; center card in content area
    black_rgb = hex_to_rgb(CARD_BG)
    canvas = Image.new("RGB", (PRINT_WIDTH_PX, PRINT_HEIGHT_PX), black_rgb)
    paste_x = PRINT_MARGIN_PX + (PRINT_CONTENT_W - card_w) // 2
    paste_y = PRINT_MARGIN_PX + max(0, (PRINT_CONTENT_H - card_h) // 2)
    canvas.paste(card_img, (paste_x, paste_y))
    return canvas


def generate_qr_card_png(vendor, menu_url: str) -> BytesIO:
    """Generate QR card as PNG bytes: 4" x 6" at 300 DPI (1200 x 1800 px). Returns BytesIO."""
    img = _build_print_image(vendor, menu_url)
    buffer = BytesIO()
    img.save(buffer, format="PNG", compress_level=6)
    buffer.seek(0)
    return buffer


def generate_qr_card_pdf(vendor, menu_url: str) -> BytesIO:
    """Generate QR card as single-page PDF: 4" x 6" at 300 DPI. Image embedded as JPEG for smaller file size. Returns BytesIO."""
    img = _build_print_image(vendor, menu_url)
    img_buffer = BytesIO()
    img.save(img_buffer, format="JPEG", quality=92)
    img_buffer.seek(0)

    pdf_buffer = BytesIO()
    page_w_pt = 4 * 72   # 4 inch
    page_h_pt = 6 * 72   # 6 inch
    c = pdf_canvas.Canvas(pdf_buffer, pagesize=(page_w_pt, page_h_pt))
    c.drawImage(
        ImageReader(img_buffer),
        0, 0,
        width=page_w_pt,
        height=page_h_pt,
        preserveAspectRatio=True,
    )
    c.save()
    pdf_buffer.seek(0)
    return pdf_buffer
