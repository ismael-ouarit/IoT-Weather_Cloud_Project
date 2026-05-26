"""
Weather Icons for M5Stack Core2 LCD (320×240).

Provides drawing functions for weather condition icons using LCD primitives.
Each icon is drawn at a given (x, y) position with a specified size.

Designed for UIFlow / M5Stack MicroPython (lcd.circle, lcd.rect, lcd.line, etc.)
Falls back to print statements when running outside the device.
"""

# ---------------------------------------------------------------------------
# Color palette (RGB565 format for M5Stack LCD)
# ---------------------------------------------------------------------------

# Theme colors
COLOR_BG        = 0x1A1A2E  # Dark navy background
COLOR_CARD_BG   = 0x16213E  # Slightly lighter card background
COLOR_PRIMARY   = 0x0F3460  # Deep blue accent
COLOR_ACCENT    = 0xE94560  # Coral/red accent
COLOR_TEXT       = 0xFFFFFF  # White text
COLOR_TEXT_DIM   = 0x8899AA  # Dimmed text
COLOR_SUCCESS    = 0x00D68F  # Green for good
COLOR_WARNING    = 0xFFAA00  # Amber for warnings
COLOR_DANGER     = 0xFF4444  # Red for alerts

# Weather-specific colors
COLOR_SUN        = 0xFFD700  # Gold sun
COLOR_SUN_RAY    = 0xFFA500  # Orange sun rays
COLOR_CLOUD      = 0xCCDDEE  # Light grey cloud
COLOR_CLOUD_DARK = 0x778899  # Dark grey cloud
COLOR_RAIN       = 0x4488FF  # Blue rain drops
COLOR_SNOW       = 0xEEEEFF  # White/blue snow
COLOR_LIGHTNING  = 0xFFFF00  # Yellow lightning

# Gauge colors
COLOR_GAUGE_GOOD     = 0x00D68F
COLOR_GAUGE_MODERATE = 0xFFAA00
COLOR_GAUGE_BAD      = 0xFF4444
COLOR_GAUGE_BG       = 0x333344

# Alert badge
COLOR_ALERT_BG  = 0xFF4444
COLOR_ALERT_FG  = 0xFFFFFF


# ---------------------------------------------------------------------------
# LCD abstraction (works on device via M5Stack LCD, prints elsewhere)
# ---------------------------------------------------------------------------

_HAS_LCD = False

try:
    from m5stack import lcd
    _HAS_LCD = True
except ImportError:
    try:
        from m5stack import *
        _HAS_LCD = True
    except ImportError:
        pass

if not _HAS_LCD:
    class _MockLCD:
        """Mock LCD for local testing — just prints draw calls."""
        def circle(self, x, y, r, color, fillcolor=None):
            pass
        def rect(self, x, y, w, h, color, fillcolor=None):
            pass
        def roundrect(self, x, y, w, h, r, color, fillcolor=None):
            pass
        def line(self, x1, y1, x2, y2, color):
            pass
        def triangle(self, x1, y1, x2, y2, x3, y3, color, fillcolor=None):
            pass
        def arc(self, x, y, r, thick, start, end, color, fillcolor=None):
            pass
        def clear(self, color=0x000000):
            pass
        def fillScreen(self, color):
            pass
        def font(self, f, **kwargs):
            pass
        def print(self, text, x, y, color=None):
            print("  LCD [{},{}]: {}".format(x, y, text))

    lcd = _MockLCD()


# ---------------------------------------------------------------------------
# Icon drawing functions
# ---------------------------------------------------------------------------

def draw_sun(x, y, size=32):
    """Draws a sun icon — circle with radiating rays."""
    r = size // 3
    lcd.circle(x, y, r, COLOR_SUN, COLOR_SUN)
    # 8 rays around the sun
    ray_len = size // 2
    import math
    for angle_deg in range(0, 360, 45):
        angle = math.radians(angle_deg)
        x1 = int(x + (r + 2) * math.cos(angle))
        y1 = int(y + (r + 2) * math.sin(angle))
        x2 = int(x + ray_len * math.cos(angle))
        y2 = int(y + ray_len * math.sin(angle))
        lcd.line(x1, y1, x2, y2, COLOR_SUN_RAY)


def draw_cloud(x, y, size=32, color=None):
    """Draws a cloud shape using overlapping circles."""
    c = color or COLOR_CLOUD
    r = size // 4
    # Three overlapping circles forming a cloud
    lcd.circle(x - r, y, r, c, c)
    lcd.circle(x + r, y, r, c, c)
    lcd.circle(x, y - r // 2, int(r * 1.2), c, c)
    # Flat bottom
    lcd.rect(x - r - r // 2, y, r * 3, r, c, c)


def draw_partly_cloudy(x, y, size=32):
    """Sun partially behind a cloud."""
    # Sun slightly offset to top-left
    draw_sun(x - size // 6, y - size // 6, size=int(size * 0.7))
    # Cloud in front, bottom-right
    draw_cloud(x + size // 8, y + size // 8, size=int(size * 0.7))


def draw_rain(x, y, size=32):
    """Cloud with rain drops."""
    draw_cloud(x, y - size // 6, size=int(size * 0.7), color=COLOR_CLOUD_DARK)
    # Rain drops
    drop_y = y + size // 4
    for dx in [-size // 4, 0, size // 4]:
        lcd.line(x + dx, drop_y, x + dx - 2, drop_y + size // 5, COLOR_RAIN)


def draw_heavy_rain(x, y, size=32):
    """Cloud with heavy rain drops."""
    draw_cloud(x, y - size // 6, size=int(size * 0.7), color=COLOR_CLOUD_DARK)
    # More rain drops
    drop_y = y + size // 4
    for dx in [-size // 3, -size // 6, 0, size // 6, size // 3]:
        lcd.line(x + dx, drop_y, x + dx - 3, drop_y + size // 4, COLOR_RAIN)
        lcd.line(x + dx - 1, drop_y + 2, x + dx - 4, drop_y + size // 4 + 2, COLOR_RAIN)


def draw_thunderstorm(x, y, size=32):
    """Cloud with lightning bolt."""
    draw_cloud(x, y - size // 5, size=int(size * 0.7), color=COLOR_CLOUD_DARK)
    # Lightning bolt (zig-zag)
    bx = x
    by = y + size // 6
    lcd.line(bx, by, bx - 4, by + size // 4, COLOR_LIGHTNING)
    lcd.line(bx - 4, by + size // 4, bx + 2, by + size // 4, COLOR_LIGHTNING)
    lcd.line(bx + 2, by + size // 4, bx - 2, by + size // 2, COLOR_LIGHTNING)


def draw_snow(x, y, size=32):
    """Cloud with snowflakes."""
    draw_cloud(x, y - size // 5, size=int(size * 0.7))
    # Snowflakes as small circles
    flake_y = y + size // 4
    for dx in [-size // 4, 0, size // 4]:
        lcd.circle(x + dx, flake_y, 2, COLOR_SNOW, COLOR_SNOW)
        lcd.circle(x + dx + size // 8, flake_y + size // 6, 2, COLOR_SNOW, COLOR_SNOW)


def draw_fog(x, y, size=32):
    """Three horizontal wavy lines."""
    for i in range(3):
        ly = y - size // 4 + i * (size // 4)
        lcd.line(x - size // 2, ly, x + size // 2, ly, COLOR_CLOUD)
        lcd.line(x - size // 2, ly + 1, x + size // 2, ly + 1, COLOR_CLOUD)


def draw_wind(x, y, size=32):
    """Three horizontal lines with curves."""
    for i in range(3):
        ly = y - size // 4 + i * (size // 4)
        lcd.line(x - size // 3, ly, x + size // 3, ly, COLOR_TEXT_DIM)


# ---------------------------------------------------------------------------
# Alert / status icons
# ---------------------------------------------------------------------------

def draw_warning_triangle(x, y, size=24):
    """Yellow warning triangle with exclamation mark."""
    h = int(size * 0.87)
    lcd.triangle(x, y - h // 2, x - size // 2, y + h // 2,
                 x + size // 2, y + h // 2, COLOR_WARNING, COLOR_WARNING)
    # Exclamation mark
    lcd.line(x, y - h // 4, x, y + h // 6, COLOR_BG)
    lcd.circle(x, y + h // 3, 2, COLOR_BG, COLOR_BG)


def draw_droplet(x, y, size=24):
    """Water droplet icon for humidity alerts."""
    # Teardrop shape: triangle top + circle bottom
    r = size // 3
    lcd.circle(x, y + r // 2, r, COLOR_RAIN, COLOR_RAIN)
    lcd.triangle(x, y - size // 2, x - r, y + r // 2,
                 x + r, y + r // 2, COLOR_RAIN, COLOR_RAIN)


# ---------------------------------------------------------------------------
# Weather condition → icon mapper
# ---------------------------------------------------------------------------

# OpenWeatherMap main condition → draw function
CONDITION_ICONS = {
    "clear":        draw_sun,
    "clouds":       draw_cloud,
    "few clouds":   draw_partly_cloudy,
    "rain":         draw_rain,
    "drizzle":      draw_rain,
    "heavy rain":   draw_heavy_rain,
    "thunderstorm": draw_thunderstorm,
    "snow":         draw_snow,
    "mist":         draw_fog,
    "fog":          draw_fog,
    "haze":         draw_fog,
    "wind":         draw_wind,
}


def draw_weather_icon(condition: str, x: int, y: int, size: int = 32):
    """
    Draws the appropriate weather icon for a given condition string.

    Args:
        condition: Weather condition (from OpenWeatherMap, case-insensitive).
        x, y: Center position.
        size: Icon size in pixels.
    """
    condition_lower = condition.lower().strip()

    # Try exact match first, then partial match
    draw_func = CONDITION_ICONS.get(condition_lower)
    if not draw_func:
        for key, func in CONDITION_ICONS.items():
            if key in condition_lower or condition_lower in key:
                draw_func = func
                break

    if draw_func:
        draw_func(x, y, size)
    else:
        # Fallback: draw a question mark cloud
        draw_cloud(x, y, size)
