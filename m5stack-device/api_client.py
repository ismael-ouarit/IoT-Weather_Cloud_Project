# M5Stack API Client — communicates with the Flask backend.
# Uses urequests (MicroPython) with fallback to standard requests.

try:
    import urequests as requests
except ImportError:
    import requests

try:
    import ujson as json
except ImportError:
    import json


# Backend URL — update this to your Cloud Run URL or local IP
API_BASE = "http://192.168.1.100:8080"  # TODO: set to your backend


def set_api_base(url):
    """Update the backend API base URL at runtime."""
    global API_BASE
    API_BASE = url.rstrip("/")


def sync_initial_state():
    """
    Fetches last known state from backend on device boot.
    Called when the device powers on to restore the display with the most
    recent readings from BigQuery (in case the device was off for a while).

    Returns:
        dict with latest sensor data, or None on failure.
    """
    try:
        print("[API] Syncing initial state from {}/latest_reading...".format(API_BASE))
        response = requests.get("{}/latest_reading".format(API_BASE))
        if response.status_code == 200:
            data = response.json()
            print("[API] Restored state: {}".format(data))
            return data
        else:
            print("[API] No initial state available (status {})".format(response.status_code))
            return None
    except Exception as e:
        print("[API] Sync error: {}".format(e))
        return None


def push_sensor_data(data):
    """
    Sends current sensor readings to backend for BigQuery storage.

    Args:
        data: dict with temperature, humidity, tvoc, eco2, motion_active
    """
    try:
        print("[API] Pushing sensor data to {}/sensor_data...".format(API_BASE))
        response = requests.post(
            "{}/sensor_data".format(API_BASE),
            json=data,
            headers={"Content-Type": "application/json"},
        )
        if response.status_code == 201:
            print("[API] Sensor data pushed successfully")
        else:
            print("[API] Push failed with status {}".format(response.status_code))
    except Exception as e:
        print("[API] Push error: {}".format(e))


def fetch_outdoor_weather(lat="46.5197", lon="6.6323"):
    """
    Fetches current outdoor weather from the backend.

    Args:
        lat, lon: Coordinates (default: Lausanne).

    Returns:
        dict with weather data (temp, condition, humidity, etc.) or None.
    """
    try:
        url = "{}/weather?lat={}&lon={}".format(API_BASE, lat, lon)
        print("[API] Fetching outdoor weather from {}...".format(url))
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            # Extract key fields for display
            main = data.get("main", {})
            weather = data.get("weather", [{}])[0]
            return {
                "outdoor_temp": main.get("temp"),
                "outdoor_humidity": main.get("humidity"),
                "outdoor_condition": weather.get("main", "Clear"),
                "outdoor_description": weather.get("description", ""),
            }
        else:
            print("[API] Weather fetch failed (status {})".format(response.status_code))
            return None
    except Exception as e:
        print("[API] Weather error: {}".format(e))
        return None


def fetch_forecast():
    """
    Fetches the weather forecast from the backend.

    Returns:
        list of dicts [{day, high, low, condition}, ...] or empty list.
    """
    try:
        url = "{}/forecast?metric=temperature&hours=72".format(API_BASE)
        print("[API] Fetching forecast from {}...".format(url))
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            # Transform SARIMA output into simplified day-by-day forecast
            timestamps = data.get("timestamps", [])
            predicted = data.get("predicted", [])

            if not timestamps or not predicted:
                return []

            # Group by day and compute high/low
            days = {}
            for ts, val in zip(timestamps, predicted):
                day = ts[:10]  # YYYY-MM-DD
                if day not in days:
                    days[day] = {"values": [], "day": day}
                days[day]["values"].append(val)

            forecast_list = []
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            for i, (day_key, day_data) in enumerate(sorted(days.items())[:3]):
                vals = day_data["values"]
                # Parse day name from date (MicroPython compatible)
                try:
                    # Simple weekday from YYYY-MM-DD using Zeller-like approach
                    parts = day_key.split("-")
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    # Python's time.mktime works in MicroPython
                    import time as _t
                    ts = _t.mktime((y, m, d, 0, 0, 0, 0, 0))
                    weekday = _t.localtime(ts)[6]
                    day_name = day_names[weekday]
                except Exception:
                    day_name = "Day {}".format(i+1)

                forecast_list.append({
                    "day": day_name,
                    "high": round(max(vals), 0),
                    "low": round(min(vals), 0),
                    "condition": "clear",  # SARIMA doesn't predict conditions
                })

            return forecast_list
        else:
            print("[API] Forecast fetch failed (status {})".format(response.status_code))
            return []
    except Exception as e:
        print("[API] Forecast error: {}".format(e))
        return []
