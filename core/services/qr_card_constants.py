"""
Design constants for QR card (PNG/PDF).
Must match React MenuQRCode.tsx exactly for 100% parity.
"""

# Colors (hex) - same as React MenuQRCode.tsx
CARD_BG = "#0a0a0a"
GOLD = "#c9a227"
WHITE = "#ffffff"
WHITE_90 = (255, 255, 255, 230)  # rgba(255,255,255,0.9) for subtitle
WHITE_70 = (255, 255, 255, 179)   # rgba(255,255,255,0.7) for footer
QR_BG = "#ffffff"
QR_FG = "#000000"

# Fallback logo colors - same 8 colors as React colorFromName
COLORS_FROM_NAME = [
    "#1C455A",
    "#2E7D32",
    "#1565C0",
    "#6A1B9A",
    "#C62828",
    "#E65100",
    "#00695C",
    "#283593",
]

# Layout (px) - same as React
CARD_WIDTH = 384
CARD_PADDING_TOP_BOTTOM = 24
CARD_PADDING_LEFT_RIGHT = 20
CARD_BORDER_RADIUS = 12

LOGO_SIZE = 72
LOGO_BORDER_WIDTH = 3

TITLE_FONT_SIZE = 22
TITLE_LETTER_SPACING_EM = 0.15
SUBTITLE_FONT_SIZE = 10
SUBTITLE_LETTER_SPACING_EM = 0.2
FOOTER_FONT_SIZE = 10

QR_MODULE_SIZE = 200
QR_CONTAINER_PADDING = 8
QR_CONTAINER_BORDER_WIDTH = 3
QR_CONTAINER_RADIUS = 8

# Scan & Order Now text (call to action above QR code)
SCAN_ORDER_FONT_SIZE = 16
SCAN_ORDER_MARGIN_BOTTOM = 12  # mb-3 equivalent

# Spacing (px) - from React mb-4, mb-0.5, mt-4 etc.
LOGO_MARGIN_BOTTOM = 16   # mb-4
TITLE_MARGIN_BOTTOM = 2   # mb-0.5
SUBTITLE_MARGIN_BOTTOM = 12  # mb-3 (updated to match React)
FOOTER_MARGIN_TOP = 16    # mt-4


def get_initials(name: str) -> str:
    """
    Get initials from vendor name. Must match React getInitials() exactly:
    first letter of first and last word, or first two chars of single word.
    """
    s = (name or "").strip()
    if not s:
        return "?"
    parts = s.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    s = parts[0]
    return (s[0] + s[1]).upper() if len(s) >= 2 else s[0].upper()


def color_from_name(name: str) -> str:
    """
    Pick a consistent color from name hash. Must match React colorFromName() exactly:
    integer hash = ((hash << 5) - hash) + charCodeAt(i), then colors[abs(hash) % length].
    """
    s = name or ""
    h = 0
    for c in s:
        h = ((h << 5) - h) + ord(c)
    idx = abs(h) % len(COLORS_FROM_NAME)
    return COLORS_FROM_NAME[idx]


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert #RRGGBB to (r, g, b)."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
