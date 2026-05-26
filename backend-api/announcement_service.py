"""
Announcement Service — generates context-aware spoken weather announcements.

Called when motion is detected (max once per hour) or on-demand.
Builds a natural-language announcement and returns it as text + MP3 audio.
"""

import os
from datetime import datetime

from bq_client import get_latest_reading
from weather_client import get_current_weather
from voice_assistant import text_to_speech


def _get_time_greeting() -> str:
    """Returns a time-appropriate greeting."""
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    elif hour < 18:
        return "Good afternoon"
    else:
        return "Good evening"


def _assess_air_quality(tvoc, eco2) -> tuple:
    """
    Returns (quality_label, is_alert) based on TVOC and eCO2 levels.
    TVOC thresholds (ppb): <65 excellent, <220 good, <660 moderate, >=660 poor
    eCO2 thresholds (ppm): <600 excellent, <800 good, <1000 moderate, >=1000 poor
    """
    if tvoc is None:
        return "unknown", False

    if tvoc >= 660 or (eco2 is not None and eco2 >= 1000):
        return "poor", True
    if tvoc >= 220 or (eco2 is not None and eco2 >= 800):
        return "moderate", False
    if tvoc >= 65:
        return "good", False
    return "excellent", False


def _check_rain(weather_data: dict) -> tuple:
    """
    Checks weather data for rain.
    Returns (is_rain, description).
    """
    if "error" in weather_data:
        return False, ""
    main = weather_data.get("weather", [{}])[0].get("main", "").lower()
    desc = weather_data.get("weather", [{}])[0].get("description", "")
    is_rain = "rain" in main or "drizzle" in main or "thunderstorm" in main
    return is_rain, desc


def generate_announcement(lat=None, lon=None) -> dict:
    """
    Generates a context-aware weather announcement.

    Returns:
        dict with 'text' (announcement string), 'audio' (MP3 bytes),
        'alerts' (list of alert strings).
    """
    lat = lat or os.environ.get("LATITUDE", "46.5197")
    lon = lon or os.environ.get("LONGITUDE", "6.6323")

    greeting = _get_time_greeting()
    parts = [f"{greeting}!"]
    alerts = []

    # --- Indoor conditions ---
    reading = get_latest_reading()
    if reading:
        temp = reading.get("temperature")
        hum = reading.get("humidity")
        tvoc = reading.get("tvoc")
        eco2 = reading.get("eco2")

        if temp is not None:
            parts.append(f"The indoor temperature is {temp}°C")

        if hum is not None:
            parts.append(f"with {hum}% humidity.")
            # Humidity alert
            if hum < 40:
                alert_msg = (
                    f"Heads up: indoor humidity is only {hum}%, "
                    "which is below the healthy threshold of 40%. "
                    "Consider using a humidifier."
                )
                parts.append(alert_msg)
                alerts.append(f"Low humidity: {hum}%")

        if tvoc is not None:
            quality, is_alert = _assess_air_quality(tvoc, eco2)
            if is_alert:
                alert_msg = (
                    f"Air quality alert! TVOC is at {tvoc} ppb, which is {quality}. "
                    "You might want to open a window for ventilation."
                )
                parts.append(alert_msg)
                alerts.append(f"Poor air quality: TVOC {tvoc} ppb")
            else:
                parts.append(f"Air quality is {quality}.")

    # --- Outdoor weather ---
    weather = get_current_weather(lat, lon)
    if "error" not in weather:
        outdoor_temp = weather.get("main", {}).get("temp")
        feels_like = weather.get("main", {}).get("feels_like")
        wind_speed = weather.get("wind", {}).get("speed", 0)
        description = weather.get("weather", [{}])[0].get("description", "")
        main_cond = weather.get("weather", [{}])[0].get("main", "").lower()

        if outdoor_temp is not None:
            parts.append(f"Outside, it's {outdoor_temp}°C with {description}.")

        hour = datetime.now().hour
        is_night = hour < 6 or hour >= 22
        is_evening = 18 <= hour < 22

        # Condition-specific advice — wording differs between day and night
        if "thunderstorm" in main_cond:
            parts.append("There's a thunderstorm outside — stay indoors if you can!")
            alerts.append(f"Thunderstorm: {description}")
        elif "snow" in main_cond:
            if is_night:
                parts.append("It's snowing tonight. Roads may be icy by morning — take care!")
            else:
                parts.append("It's snowing outside. Roads may be slippery — take care if you're driving!")
            alerts.append(f"Snow: {description}")
        elif "rain" in main_cond or "drizzle" in main_cond:
            if is_night:
                parts.append("It's raining outside. Take an umbrella if you're heading out.")
            else:
                parts.append("It's raining outside — don't forget your umbrella!")
            alerts.append(f"Rain: {description}")
        elif "fog" in main_cond or "mist" in main_cond or "haze" in main_cond:
            if is_night:
                parts.append("Visibility is low tonight due to fog — be careful if you're driving.")
            else:
                parts.append("Visibility is low due to fog. Take it slow if you're heading out.")
        elif "clear" in main_cond:
            if is_night:
                parts.append("Clear skies tonight — good conditions if you need to head out.")
            elif is_evening:
                parts.append("It's clear this evening.")
            else:
                parts.append("It's clear outside — great weather to step out!")
        elif "cloud" in main_cond:
            if is_night:
                parts.append("Cloudy skies tonight.")
            else:
                parts.append("It's cloudy out there.")

        # Temperature advice — day vs night framing
        if outdoor_temp is not None:
            if outdoor_temp <= 0:
                if is_night:
                    parts.append("It's freezing outside — watch out for ice if you head out.")
                else:
                    parts.append("It's freezing — watch out for ice on the ground!")
            elif outdoor_temp < 10:
                if is_night:
                    parts.append("It's quite cold tonight — bundle up if you're going out.")
                else:
                    parts.append("Dress warmly, it's quite cold outside.")
            elif outdoor_temp < 16:
                if not is_night:
                    parts.append("A jacket would be a good idea today.")
            elif outdoor_temp > 35:
                if not is_night:
                    parts.append("It's extremely hot — avoid direct sun and drink plenty of water!")
            elif outdoor_temp > 28:
                if is_night:
                    parts.append("It's a warm night outside.")
                else:
                    parts.append("It's hot outside. Stay hydrated and wear light clothing.")

        # Wind advice
        if wind_speed >= 10:
            if is_night:
                parts.append(f"It's also quite windy tonight at {wind_speed} m/s.")
            else:
                parts.append(f"It's also quite windy at {wind_speed} m/s — hold onto your hat!")

    announcement_text = " ".join(parts)

    # Generate audio
    try:
        audio = text_to_speech(announcement_text)
    except Exception as e:
        print(f"TTS error during announcement: {e}")
        audio = None

    return {
        "text": announcement_text,
        "audio": audio,
        "alerts": alerts,
        "timestamp": datetime.utcnow().isoformat(),
    }
