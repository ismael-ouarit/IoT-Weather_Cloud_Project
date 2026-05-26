"""
Display Module for M5Stack Core2 (320×240 LCD).

Provides a polished, multi-screen weather station interface with:
  - Screen 0: HOME     — date/time, outdoor weather icon + temp, indoor temp & humidity
  - Screen 1: AIR      — TVOC and eCO2 gauges with color-coded quality
  - Screen 2: FORECAST — 3-day weather forecast with icons
  - Screen 3: ALERTS   — active alerts panel

Uses a dark theme with accent colors for a professional look.
"""

import time as _time

from icons import (
    lcd,
    COLOR_BG, COLOR_CARD_BG, COLOR_PRIMARY, COLOR_ACCENT,
    COLOR_TEXT, COLOR_TEXT_DIM, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER,
    COLOR_GAUGE_GOOD, COLOR_GAUGE_MODERATE, COLOR_GAUGE_BAD, COLOR_GAUGE_BG,
    COLOR_ALERT_BG, COLOR_ALERT_FG, COLOR_SUN, COLOR_RAIN,
    draw_weather_icon, draw_warning_triangle, draw_droplet,
)

# ---------------------------------------------------------------------------
# Screen dimensions & layout constants
# ---------------------------------------------------------------------------
SCREEN_W = 320
SCREEN_H = 240
STATUS_BAR_H = 20
NAV_BAR_H = 30
CONTENT_Y = STATUS_BAR_H + 4
CONTENT_H = SCREEN_H - STATUS_BAR_H - NAV_BAR_H - 8

# Screen indices
SCREEN_HOME     = 0
SCREEN_AIR      = 1
SCREEN_FORECAST = 2
SCREEN_ALERTS   = 3
NUM_SCREENS     = 4

SCREEN_TITLES = ["Home", "Air Quality", "Forecast", "Alerts"]


# ---------------------------------------------------------------------------
# Font helpers (M5Stack UIFlow fonts)
# ---------------------------------------------------------------------------

def _set_font_large():
    """Large font for main readings."""
    try:
        lcd.font(lcd.FONT_DejaVu24)
    except Exception:
        pass

def _set_font_medium():
    """Medium font for labels."""
    try:
        lcd.font(lcd.FONT_DejaVu18)
    except Exception:
        pass

def _set_font_small():
    """Small font for status bar and details."""
    try:
        lcd.font(lcd.FONT_Default)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Common UI elements
# ---------------------------------------------------------------------------

def draw_status_bar(time_str="--:--", wifi_ok=True, screen_idx=0):
    """
    Top status bar: WiFi indicator, screen title, time.
    """
    lcd.rect(0, 0, SCREEN_W, STATUS_BAR_H, COLOR_PRIMARY, COLOR_PRIMARY)
    _set_font_small()

    # WiFi icon (simple dot indicator)
    wifi_color = COLOR_SUCCESS if wifi_ok else COLOR_DANGER
    lcd.circle(10, STATUS_BAR_H // 2, 4, wifi_color, wifi_color)

    # Screen title
    title = SCREEN_TITLES[screen_idx] if screen_idx < len(SCREEN_TITLES) else ""
    lcd.print(title, SCREEN_W // 2 - len(title) * 3, 3, COLOR_TEXT)

    # Time
    lcd.print(time_str, SCREEN_W - 50, 3, COLOR_TEXT)


def draw_nav_bar(current_screen=0):
    """
    Bottom navigation bar with 4 dots indicating current screen.
    """
    bar_y = SCREEN_H - NAV_BAR_H
    lcd.rect(0, bar_y, SCREEN_W, NAV_BAR_H, COLOR_BG, COLOR_BG)

    # Navigation dots
    dot_spacing = 20
    start_x = SCREEN_W // 2 - (NUM_SCREENS - 1) * dot_spacing // 2
    dot_y = bar_y + NAV_BAR_H // 2

    for i in range(NUM_SCREENS):
        dot_x = start_x + i * dot_spacing
        if i == current_screen:
            lcd.circle(dot_x, dot_y, 5, COLOR_ACCENT, COLOR_ACCENT)
        else:
            lcd.circle(dot_x, dot_y, 3, COLOR_TEXT_DIM, COLOR_TEXT_DIM)

    # Swipe hint labels
    _set_font_small()
    if current_screen > 0:
        lcd.print("<", 8, bar_y + 8, COLOR_TEXT_DIM)
    if current_screen < NUM_SCREENS - 1:
        lcd.print(">", SCREEN_W - 16, bar_y + 8, COLOR_TEXT_DIM)

    # Voice button hint (center)
    lcd.rect(SCREEN_W // 2 - 25, bar_y + 3, 50, NAV_BAR_H - 6, 8,
                  COLOR_ACCENT, COLOR_ACCENT)
    lcd.print("ASK", SCREEN_W // 2 - 10, bar_y + 8, COLOR_TEXT)


def draw_card(x, y, w, h, title=""):
    """Draws a rounded card background with optional title."""
    lcd.rect(x, y, w, h, COLOR_CARD_BG, COLOR_CARD_BG)
    if title:
        _set_font_small()
        lcd.print(title, x + 8, y + 4, COLOR_TEXT_DIM)


# ---------------------------------------------------------------------------
# Screen 0: HOME
# ---------------------------------------------------------------------------

def draw_home_screen(data):
    """
    Main home screen showing:
    - Current date and time (large)
    - Outdoor weather icon + temperature
    - Indoor temperature and humidity

    Args:
        data: dict with keys:
            - time_str, date_str: formatted time and date
            - outdoor_temp, outdoor_condition: outdoor weather
            - temperature, humidity: indoor readings
    """
    lcd.clear(COLOR_BG)

    time_str = data.get("time_str", "--:--")
    date_str = data.get("date_str", "----/--/--")
    outdoor_temp = data.get("outdoor_temp")
    outdoor_cond = data.get("outdoor_condition", "clear")
    indoor_temp = data.get("temperature")
    indoor_hum = data.get("humidity")

    draw_status_bar(time_str=time_str, screen_idx=SCREEN_HOME)

    # ── Date & Time (top center) ──────────────────────────────────────────
    _set_font_large()
    lcd.print(time_str, SCREEN_W // 2 - 40, CONTENT_Y + 5, COLOR_TEXT)
    _set_font_small()
    lcd.print(date_str, SCREEN_W // 2 - 35, CONTENT_Y + 32, COLOR_TEXT_DIM)

    # ── Outdoor card (left half) ──────────────────────────────────────────
    card_y = CONTENT_Y + 52
    card_h = 100
    draw_card(8, card_y, SCREEN_W // 2 - 12, card_h, "OUTDOOR")

    # Weather icon
    draw_weather_icon(outdoor_cond, 50, card_y + 50, size=40)

    # Outdoor temperature
    if outdoor_temp is not None:
        _set_font_large()
        lcd.print("{}".format(int(outdoor_temp)), 90, card_y + 35, COLOR_TEXT)
        _set_font_small()
        lcd.print("°C", 130, card_y + 35, COLOR_TEXT_DIM)
    else:
        _set_font_medium()
        lcd.print("--", 90, card_y + 40, COLOR_TEXT_DIM)

    # Condition text
    _set_font_small()
    lcd.print(outdoor_cond.capitalize()[:12], 30, card_y + 78, COLOR_TEXT_DIM)

    # ── Indoor card (right half) ──────────────────────────────────────────
    draw_card(SCREEN_W // 2 + 4, card_y, SCREEN_W // 2 - 12, card_h, "INDOOR")

    ix = SCREEN_W // 2 + 20

    # Temperature
    if indoor_temp is not None:
        _set_font_large()
        lcd.print("{}".format(round(indoor_temp, 1)), ix, card_y + 28, COLOR_TEXT)
        _set_font_small()
        lcd.print("°C", ix + 60, card_y + 28, COLOR_TEXT_DIM)

        # Color-coded indicator
        if indoor_temp < 18:
            temp_color = COLOR_RAIN
        elif indoor_temp > 28:
            temp_color = COLOR_DANGER
        else:
            temp_color = COLOR_SUCCESS
        lcd.circle(ix + 80, card_y + 35, 4, temp_color, temp_color)

    # Humidity
    if indoor_hum is not None:
        _set_font_medium()
        lcd.print("{}%".format(int(indoor_hum)), ix + 10, card_y + 60, COLOR_TEXT)

        # Humidity alert indicator
        if indoor_hum < 40:
            lcd.print("LOW", ix + 55, card_y + 62, COLOR_WARNING)
            draw_droplet(ix + 85, card_y + 68, 16)
        else:
            _set_font_small()
            lcd.print("humidity", ix + 10, card_y + 80, COLOR_TEXT_DIM)

    draw_nav_bar(SCREEN_HOME)


# ---------------------------------------------------------------------------
# Screen 1: AIR QUALITY
# ---------------------------------------------------------------------------

def _gauge_color(value, thresholds):
    """Returns color based on value and (good, moderate) thresholds."""
    if value < thresholds[0]:
        return COLOR_GAUGE_GOOD
    elif value < thresholds[1]:
        return COLOR_GAUGE_MODERATE
    return COLOR_GAUGE_BAD


def _draw_gauge(x, y, w, h, value, max_val, label, unit, thresholds):
    """Draws a horizontal gauge bar with label and value."""
    draw_card(x, y, w, h, label)

    bar_x = x + 10
    bar_y_pos = y + 22
    bar_w = w - 20
    bar_h = 14

    # Background bar
    lcd.rect(bar_x, bar_y_pos, bar_w, bar_h, COLOR_GAUGE_BG, COLOR_GAUGE_BG)

    # Filled portion
    if value is not None and max_val > 0:
        fill_w = min(int((value / max_val) * bar_w), bar_w)
        color = _gauge_color(value, thresholds)
        lcd.rect(bar_x, bar_y_pos, fill_w, bar_h, color, color)

        # Value text
        _set_font_medium()
        lcd.print("{}".format(value), x + 10, y + 42, COLOR_TEXT)
        _set_font_small()
        lcd.print(unit, x + 60, y + 44, COLOR_TEXT_DIM)

        # Quality label
        if value < thresholds[0]:
            qlabel, qcolor = "Excellent", COLOR_GAUGE_GOOD
        elif value < thresholds[1]:
            qlabel, qcolor = "Moderate", COLOR_GAUGE_MODERATE
        else:
            qlabel, qcolor = "Poor!", COLOR_GAUGE_BAD
        lcd.print(qlabel, x + w - 60, y + 44, qcolor)
    else:
        _set_font_medium()
        lcd.print("--", x + 10, y + 42, COLOR_TEXT_DIM)


def draw_air_quality_screen(data):
    """
    Air quality screen with TVOC and eCO2 gauges.

    Args:
        data: dict with 'tvoc', 'eco2', 'time_str'
    """
    lcd.clear(COLOR_BG)
    time_str = data.get("time_str", "--:--")
    draw_status_bar(time_str=time_str, screen_idx=SCREEN_AIR)

    tvoc = data.get("tvoc")
    eco2 = data.get("eco2")

    # Title
    _set_font_medium()
    lcd.print("Indoor Air Quality", 70, CONTENT_Y + 5, COLOR_TEXT)

    # TVOC gauge — thresholds: <65 good, <220 moderate, >=220 poor
    _draw_gauge(
        x=10, y=CONTENT_Y + 30, w=SCREEN_W - 20, h=65,
        value=tvoc, max_val=1000,
        label="TVOC (Volatile Compounds)",
        unit="ppb",
        thresholds=(65, 220),
    )

    # eCO2 gauge — thresholds: <600 good, <1000 moderate, >=1000 poor
    _draw_gauge(
        x=10, y=CONTENT_Y + 105, w=SCREEN_W - 20, h=65,
        value=eco2, max_val=2000,
        label="eCO2 (Carbon Dioxide Equiv.)",
        unit="ppm",
        thresholds=(600, 1000),
    )

    draw_nav_bar(SCREEN_AIR)


# ---------------------------------------------------------------------------
# Screen 2: FORECAST
# ---------------------------------------------------------------------------

def draw_forecast_screen(data):
    """
    3-day forecast screen with weather icons.

    Args:
        data: dict with 'forecast' list of dicts:
            [{day: 'Mon', high: 22, low: 14, condition: 'rain'}, ...]
            and 'time_str'
    """
    lcd.clear(COLOR_BG)
    time_str = data.get("time_str", "--:--")
    draw_status_bar(time_str=time_str, screen_idx=SCREEN_FORECAST)

    forecast_list = data.get("forecast", [])

    _set_font_medium()
    lcd.print("Weather Forecast", 80, CONTENT_Y + 5, COLOR_TEXT)

    if not forecast_list:
        _set_font_small()
        lcd.print("No forecast data available", 60, CONTENT_Y + 80, COLOR_TEXT_DIM)
        draw_nav_bar(SCREEN_FORECAST)
        return

    # Show up to 3 days in horizontal cards
    card_w = (SCREEN_W - 30) // min(len(forecast_list), 3)
    card_h = 130
    card_y = CONTENT_Y + 30

    for i, fc in enumerate(forecast_list[:3]):
        cx = 10 + i * (card_w + 5)
        draw_card(cx, card_y, card_w - 5, card_h, fc.get("day", "Day {}".format(i+1)))

        # Weather icon
        icon_x = cx + card_w // 2 - 2
        draw_weather_icon(fc.get("condition", "clear"), icon_x, card_y + 40, size=30)

        # High/Low temperatures
        _set_font_medium()
        high = fc.get("high", "--")
        low = fc.get("low", "--")
        lcd.print("{}°".format(high), cx + 10, card_y + 70, COLOR_TEXT)
        _set_font_small()
        lcd.print("{}°".format(low), cx + 10, card_y + 92, COLOR_TEXT_DIM)

        # Condition text
        cond = fc.get("condition", "")[:10]
        lcd.print(cond, cx + 8, card_y + 110, COLOR_TEXT_DIM)

    draw_nav_bar(SCREEN_FORECAST)


# ---------------------------------------------------------------------------
# Screen 3: ALERTS
# ---------------------------------------------------------------------------

def draw_alerts_screen(data):
    """
    Active alerts panel.

    Args:
        data: dict with 'alerts' list of strings, 'time_str'
    """
    lcd.clear(COLOR_BG)
    time_str = data.get("time_str", "--:--")
    draw_status_bar(time_str=time_str, screen_idx=SCREEN_ALERTS)

    alerts = data.get("alerts", [])

    _set_font_medium()
    lcd.print("Active Alerts", 90, CONTENT_Y + 5, COLOR_TEXT)

    if not alerts:
        # All clear!
        lcd.circle(SCREEN_W // 2, CONTENT_Y + 80, 20, COLOR_SUCCESS, COLOR_SUCCESS)
        _set_font_small()
        lcd.print("✓", SCREEN_W // 2 - 5, CONTENT_Y + 74, COLOR_TEXT)
        _set_font_medium()
        lcd.print("All Clear", SCREEN_W // 2 - 35, CONTENT_Y + 110, COLOR_SUCCESS)
        _set_font_small()
        lcd.print("No active alerts", SCREEN_W // 2 - 45, CONTENT_Y + 135, COLOR_TEXT_DIM)
        draw_nav_bar(SCREEN_ALERTS)
        return

    # Show each alert in a card
    alert_y = CONTENT_Y + 30
    for i, alert_text in enumerate(alerts[:4]):  # max 4 alerts visible
        card_y = alert_y + i * 38
        draw_card(10, card_y, SCREEN_W - 20, 34, "")

        # Warning icon
        draw_warning_triangle(28, card_y + 17, 18)

        # Alert text
        _set_font_small()
        lcd.print(alert_text[:38], 44, card_y + 8, COLOR_WARNING)

    draw_nav_bar(SCREEN_ALERTS)


# ---------------------------------------------------------------------------
# Voice recording overlay
# ---------------------------------------------------------------------------

def draw_voice_recording_overlay():
    """Shows a recording indicator overlay when the user taps ASK."""
    # Semi-transparent overlay (draw a dark rect)
    lcd.rect(40, 70, SCREEN_W - 80, 100, COLOR_CARD_BG, COLOR_CARD_BG)
    lcd.rect(40, 70, SCREEN_W - 80, 100, COLOR_ACCENT)

    # Pulsing mic indicator
    lcd.circle(SCREEN_W // 2, 105, 15, COLOR_ACCENT, COLOR_ACCENT)
    _set_font_small()
    lcd.print("●", SCREEN_W // 2 - 4, 99, COLOR_TEXT)

    _set_font_medium()
    lcd.print("Listening...", SCREEN_W // 2 - 42, 130, COLOR_TEXT)
    _set_font_small()
    lcd.print("Speak your question", SCREEN_W // 2 - 55, 150, COLOR_TEXT_DIM)


def draw_voice_answer_overlay(answer_text):
    """Shows the voice answer text before/while playing audio."""
    lcd.rect(20, 50, SCREEN_W - 40, 140, COLOR_CARD_BG, COLOR_CARD_BG)
    lcd.rect(20, 50, SCREEN_W - 40, 140, COLOR_PRIMARY)

    _set_font_small()
    lcd.print("Answer:", 35, 60, COLOR_ACCENT)

    # Word-wrap the answer text (max ~35 chars per line)
    y_pos = 80
    words = answer_text.split()
    line = ""
    for word in words:
        if len(line) + len(word) + 1 > 35:
            lcd.print(line, 35, y_pos, COLOR_TEXT)
            y_pos += 16
            line = word
            if y_pos > 170:
                lcd.print("...", 35, y_pos, COLOR_TEXT_DIM)
                break
        else:
            line = "{} {}".format(line, word).strip()
    if line and y_pos <= 170:
        lcd.print(line, 35, y_pos, COLOR_TEXT)


# ---------------------------------------------------------------------------
# Main update dispatcher
# ---------------------------------------------------------------------------

def update_screen(data, screen_idx=0):
    """
    Renders the appropriate screen based on screen_idx.

    Args:
        data: dict containing all sensor/weather/alert data.
        screen_idx: 0=Home, 1=Air, 2=Forecast, 3=Alerts
    """
    if screen_idx == SCREEN_HOME:
        draw_home_screen(data)
    elif screen_idx == SCREEN_AIR:
        draw_air_quality_screen(data)
    elif screen_idx == SCREEN_FORECAST:
        draw_forecast_screen(data)
    elif screen_idx == SCREEN_ALERTS:
        draw_alerts_screen(data)
    else:
        draw_home_screen(data)
