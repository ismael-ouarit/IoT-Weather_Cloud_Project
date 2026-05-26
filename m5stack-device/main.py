"""
M5Stack Core2 Weather Station — Main Application.

Features:
  - 4-screen swipe navigation (Home, Air Quality, Forecast, Alerts)
  - NTP time synchronization
  - Sensor readings every 60 seconds, pushed to backend
  - Motion-triggered weather announcements (max once per hour)
  - Voice query via touchscreen "ASK" button
  - Syncs last known state from BigQuery on boot
"""

import time


from wifi_manager import connect_wifi
from sensors import read_all_sensors
from api_client import (
    sync_initial_state,
    push_sensor_data,
    fetch_outdoor_weather,
    fetch_forecast,
    set_api_base,
)
from display import (
    update_screen,
    draw_voice_recording_overlay,
    draw_voice_answer_overlay,
    NUM_SCREENS,
)
from voice import (
    do_voice_interaction,
    do_motion_announcement,
    set_api_base as voice_set_api_base,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Backend API URL — change this to your Cloud Run URL or local IP
BACKEND_URL = "http://localhost:8080"  # TODO: update for your setup

# Coordinates for weather (Lausanne default)
LATITUDE = "46.5197"
LONGITUDE = "6.6323"

# Timing intervals (seconds)
SENSOR_INTERVAL = 60          # Read sensors every 60s
WEATHER_INTERVAL = 300        # Fetch outdoor weather every 5 min
FORECAST_INTERVAL = 1800      # Fetch forecast every 30 min
ANNOUNCEMENT_COOLDOWN = 3600  # Max one announcement per hour

# ---------------------------------------------------------------------------
# NTP Time Sync
# ---------------------------------------------------------------------------

def sync_ntp():
    """Syncs the device clock with NTP servers."""
    try:
        import ntptime
        ntptime.settime()
        print("[NTP] Time synchronized successfully")
    except ImportError:
        print("[NTP] ntptime not available — using system time")
    except Exception as e:
        print("[NTP] Sync failed: {}".format(e))


def get_time_strings():
    """Returns formatted time and date strings using MicroPython time."""
    try:
        t = time.localtime()
        # localtime returns: (year, month, mday, hour, minute, second, weekday, yearday)
        time_str = "{:02d}:{:02d}".format(t[3], t[4])
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        date_str = "{} {:02d} {} {}".format(days[t[6]], t[2], months[t[1]-1], t[0])
        return time_str, date_str
    except Exception:
        return "--:--", "----/--/--"


# ---------------------------------------------------------------------------
# Touch input (screen navigation + ASK button)
# ---------------------------------------------------------------------------

_HAS_TOUCH = False
try:
    from m5stack import touch
    _HAS_TOUCH = True
except ImportError:
    pass


def check_touch():
    """
    Checks for touch input on the M5Stack Core2 touchscreen.

    Returns:
        'left'  — swipe left (next screen)
        'right' — swipe right (previous screen)
        'ask'   — tapped the ASK button (center bottom)
        None    — no touch
    """
    if not _HAS_TOUCH:
        return None

    try:
        if touch.status():
            x, y = touch.read()

            # ASK button area (center bottom nav bar)
            if y > 210 and 120 < x < 200:
                return "ask"

            # Swipe zones
            if y > 30 and y < 210:
                if x < 60:
                    return "right"  # Swipe from left edge = go back
                if x > 260:
                    return "left"   # Swipe from right edge = go forward

        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Alert generation
# ---------------------------------------------------------------------------

def generate_alerts(sensor_data, outdoor_data=None):
    """
    Generates alert messages based on current readings.

    Returns:
        list of alert strings.
    """
    alerts = []

    # Humidity alert (<40%)
    hum = sensor_data.get("humidity")
    if hum is not None and hum < 40:
        alerts.append("Low humidity: {}% (below 40%)".format(hum))

    # Air quality alerts
    tvoc = sensor_data.get("tvoc")
    eco2 = sensor_data.get("eco2")

    if tvoc is not None and tvoc >= 220:
        if tvoc >= 660:
            alerts.append("Poor air quality! TVOC: {} ppb".format(tvoc))
        else:
            alerts.append("Moderate air quality: TVOC {} ppb".format(tvoc))

    if eco2 is not None and eco2 >= 1000:
        alerts.append("High CO2 levels: {} ppm".format(eco2))

    # High temperature alert
    temp = sensor_data.get("temperature")
    if temp is not None and temp > 30:
        alerts.append("High indoor temperature: {}°C".format(temp))

    # Outdoor rain alert
    if outdoor_data:
        cond = outdoor_data.get("outdoor_condition", "").lower()
        if "rain" in cond or "drizzle" in cond or "thunderstorm" in cond:
            alerts.append("Rain outside: {}".format(outdoor_data.get('outdoor_description', cond)))

    return alerts


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

def setup():
    """Initialize the weather station."""
    print("=" * 50)
    print("  M5Stack Core2 Weather Station")
    print("  Initializing...")
    print("=" * 50)

    # Set backend URL for all modules
    set_api_base(BACKEND_URL)
    voice_set_api_base(BACKEND_URL)

    # Connect to WiFi
    connect_wifi()

    # Sync NTP time
    sync_ntp()

    # Sync last known state from BigQuery
    last_state = sync_initial_state()
    if last_state:
        print("[SETUP] Restored previous state from BigQuery")
        return last_state

    return {}


def loop():
    """Main application loop."""
    # Initial state
    current_screen = 0
    last_sensor_time = 0
    last_weather_time = 0
    last_forecast_time = 0
    last_announcement_time = 0

    # Data stores
    sensor_data = {}
    outdoor_data = {}
    forecast_data = []
    alerts = []

    # Get initial state
    initial_state = setup()
    if initial_state:
        sensor_data.update(initial_state)

    print("[MAIN] Entering main loop...")
    print("[MAIN] Press Ctrl+C to exit")

    while True:
        try:
            now = time.time()
            time_str, date_str = get_time_strings()

            # ── Read sensors (every SENSOR_INTERVAL seconds) ──────────
            if now - last_sensor_time >= SENSOR_INTERVAL:
                sensor_data = read_all_sensors()
                sensor_data["time_str"] = time_str
                sensor_data["date_str"] = date_str
                print("[MAIN] Sensors: T={}°C H={}% TVOC={} Motion={}".format(
                    sensor_data.get('temperature'),
                    sensor_data.get('humidity'),
                    sensor_data.get('tvoc'),
                    'Y' if sensor_data.get('motion_active') else 'N'))

                # Push to backend
                push_data = {
                    "temperature": sensor_data.get("temperature"),
                    "humidity": sensor_data.get("humidity"),
                    "tvoc": sensor_data.get("tvoc"),
                    "eco2": sensor_data.get("eco2"),
                }
                push_sensor_data(push_data)
                last_sensor_time = now

            # ── Fetch outdoor weather (every WEATHER_INTERVAL seconds) ─
            if now - last_weather_time >= WEATHER_INTERVAL:
                new_outdoor = fetch_outdoor_weather(lat=LATITUDE, lon=LONGITUDE)
                if new_outdoor:
                    outdoor_data = new_outdoor
                    print("[MAIN] Outdoor: {}°C, {}".format(
                        outdoor_data.get('outdoor_temp'),
                        outdoor_data.get('outdoor_condition')))
                last_weather_time = now

            # ── Fetch forecast (every FORECAST_INTERVAL seconds) ──────
            if now - last_forecast_time >= FORECAST_INTERVAL:
                new_forecast = fetch_forecast()
                if new_forecast:
                    forecast_data = new_forecast
                    print("[MAIN] Forecast: {} days loaded".format(len(forecast_data)))
                last_forecast_time = now

            # ── Generate alerts ───────────────────────────────────────
            alerts = generate_alerts(sensor_data, outdoor_data)

            # ── Build display data ────────────────────────────────────
            display_data = sensor_data.copy()
            display_data.update(outdoor_data)
            display_data["time_str"] = time_str
            display_data["date_str"] = date_str
            display_data["forecast"] = forecast_data
            display_data["alerts"] = alerts

            # ── Update the screen ─────────────────────────────────────
            update_screen(display_data, screen_idx=current_screen)

            # ── Motion detection → announcement ───────────────────────
            if sensor_data.get("motion_active"):
                if now - last_announcement_time >= ANNOUNCEMENT_COOLDOWN:
                    print("[MAIN] Motion detected — triggering announcement")
                    result = do_motion_announcement(lat=LATITUDE, lon=LONGITUDE)
                    if result:
                        # Show the announcement text briefly
                        draw_voice_answer_overlay(result.get("text", ""))
                        time.sleep(3)
                        # Refresh screen
                        update_screen(display_data, screen_idx=current_screen)
                    last_announcement_time = now
                else:
                    remaining = int(ANNOUNCEMENT_COOLDOWN - (now - last_announcement_time))
                    print("[MAIN] Motion detected but announcement cooldown ({}s remaining)".format(remaining))

            # ── Handle touch input ────────────────────────────────────
            touch_action = check_touch()
            if touch_action == "left":
                current_screen = (current_screen + 1) % NUM_SCREENS
                print("[MAIN] Swiped to screen {}".format(current_screen))
                update_screen(display_data, screen_idx=current_screen)

            elif touch_action == "right":
                current_screen = (current_screen - 1) % NUM_SCREENS
                print("[MAIN] Swiped to screen {}".format(current_screen))
                update_screen(display_data, screen_idx=current_screen)

            elif touch_action == "ask":
                print("[MAIN] ASK button pressed — starting voice interaction")
                draw_voice_recording_overlay()
                result = do_voice_interaction()
                if result:
                    draw_voice_answer_overlay(result.get("answer", "No answer"))
                    time.sleep(5)  # Show answer for 5 seconds
                # Refresh the current screen
                update_screen(display_data, screen_idx=current_screen)

            # Short sleep for responsive touch handling
            time.sleep(0.2)

        except KeyboardInterrupt:
            print("\n[MAIN] Shutting down...")
            break
        except Exception as e:
            print("[MAIN] Error in main loop: {}".format(e))
            time.sleep(5)


if __name__ == '__main__':
    loop()
