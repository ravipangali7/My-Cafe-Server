"""
Auto-generated logo from vendor name (initials on colored background).
Used when vendor has no uploaded logo - for API logo_url, QR downloads, and invoices.
"""
from io import BytesIO
import hashlib
from PIL import Image, ImageDraw, ImageFont


# Palette of readable, professional colors (hex)
LOGO_COLORS = [
    '#1C455A',  # dark blue
    '#2E7D32',  # green
    '#1565C0',  # blue
    '#6A1B9A',  # purple
    '#C62828',  # red
    '#E65100',  # orange
    '#00695C',  # teal
    '#283593',  # indigo
]


def _get_initials(name):
    """Get initials from vendor name: first letter of each word, or first 2 chars."""
    if not name or not name.strip():
        return '?'
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    if len(parts) == 1:
        s = parts[0]
        if len(s) >= 2:
            return (s[0] + s[1]).upper()
        return s[0].upper()
    return '?'


def _color_from_name(name):
    """Pick a consistent color from name hash."""
    h = hashlib.md5((name or '').encode()).hexdigest()
    idx = int(h[:8], 16) % len(LOGO_COLORS)
    return LOGO_COLORS[idx]


def generate_logo_image(vendor_name, size=(256, 256)):
    """
    Generate a PNG logo image from vendor name.
    Returns BytesIO containing PNG bytes.
    """
    width, height = size
    initials = _get_initials(vendor_name)
    bg_color = _color_from_name(vendor_name)

    # RGB tuple from hex
    hex_color = bg_color.lstrip('#')
    bg_rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    img = Image.new('RGB', (width, height), color=bg_rgb)
    draw = ImageDraw.Draw(img)

    # Draw circle (optional: draw in center for rounded look - we use full image as "circle" by making it square)
    # For a clear circle, we could draw an ellipse; here we keep full square for simplicity and clarity
    # Draw rounded rectangle for softer look
    margin = max(2, width // 32)
    draw.rounded_rectangle(
        [margin, margin, width - margin, height - margin],
        radius=width // 8,
        outline=(255, 255, 255),
        width=max(1, width // 128),
        fill=bg_rgb
    )

    # Text: try to load a nice font, fallback to default
    font_size = int(min(width, height) * 0.4)
    font = None
    for path in (
        "arial.ttf",
        "Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ):
        try:
            font = ImageFont.truetype(path, font_size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()

    # Get text bbox for centering (textbbox can fail with default font)
    try:
        bbox = draw.textbbox((0, 0), initials, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (width - tw) // 2 - bbox[0]
        y = (height - th) // 2 - bbox[1]
    except (TypeError, AttributeError):
        x = max(0, (width - 40) // 2)
        y = max(0, (height - 20) // 2)

    draw.text((x, y), initials, fill=(255, 255, 255), font=font)

    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer
