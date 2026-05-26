import requests
import os
from collections import Counter
from datetime import datetime


def get_current_weather(lat, lon):
    """
    Fetches the current weather and forecast for given coordinates via OpenWeatherMap.
    """
    api_key = os.environ.get("OPENWEATHERMAP_API_KEY", "")
    if not api_key:
        return {"error": "API Key missing for OpenWeatherMap"}
        
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_5day_forecast(lat, lon):
    """
    Fetches OWM's free 5-day / 3-hour forecast and aggregates it into 5 daily summaries.
    Returns a dict with a 'forecast' list of {day, date, high, low, condition} entries
    (one per day, ordered chronologically), or {"error": ...}.
    """
    api_key = os.environ.get("OPENWEATHERMAP_API_KEY", "")
    if not api_key:
        return {"error": "API Key missing for OpenWeatherMap"}

    url = (
        f"https://api.openweathermap.org/data/2.5/forecast"
        f"?lat={lat}&lon={lon}&appid={api_key}&units=metric"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e)}

    # Group 3-hour slots by date.
    by_day = {}
    for item in data.get("list", []):
        ts = item.get("dt_txt", "")[:10]  # 'YYYY-MM-DD'
        if not ts:
            continue
        main = item.get("main", {})
        cond = (item.get("weather") or [{}])[0].get("main", "")
        bucket = by_day.setdefault(ts, {"highs": [], "lows": [], "conds": []})
        if main.get("temp_max") is not None:
            bucket["highs"].append(main["temp_max"])
        if main.get("temp_min") is not None:
            bucket["lows"].append(main["temp_min"])
        if cond:
            bucket["conds"].append(cond)

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    forecast = []
    for date_str in sorted(by_day.keys())[:5]:
        bucket = by_day[date_str]
        if not bucket["highs"] or not bucket["lows"]:
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            day = day_names[dt.weekday()]
        except Exception:
            day = date_str[5:]
        # Most-frequent condition wins (e.g. "Clouds" beats one stray "Clear" slot).
        dominant_cond = Counter(bucket["conds"]).most_common(1)[0][0] if bucket["conds"] else ""
        forecast.append({
            "day": day,
            "date": date_str,
            "high": round(max(bucket["highs"])),
            "low": round(min(bucket["lows"])),
            "condition": dominant_cond,
        })

    return {"forecast": forecast, "city": data.get("city", {}).get("name", "")}


def get_5day_forecast_by_city(city_name):
    """
    Fetches OWM's 5-day / 3-hour forecast by city name and aggregates into daily summaries.
    Returns the same shape as get_5day_forecast: {"forecast": [...], "city": "..."}.
    """
    api_key = os.environ.get("OPENWEATHERMAP_API_KEY", "")
    if not api_key:
        return {"error": "API Key missing for OpenWeatherMap"}

    url = (
        f"https://api.openweathermap.org/data/2.5/forecast"
        f"?q={city_name}&appid={api_key}&units=metric"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e)}

    by_day = {}
    for item in data.get("list", []):
        ts = item.get("dt_txt", "")[:10]
        if not ts:
            continue
        main = item.get("main", {})
        cond = (item.get("weather") or [{}])[0].get("main", "")
        bucket = by_day.setdefault(ts, {"highs": [], "lows": [], "conds": []})
        if main.get("temp_max") is not None:
            bucket["highs"].append(main["temp_max"])
        if main.get("temp_min") is not None:
            bucket["lows"].append(main["temp_min"])
        if cond:
            bucket["conds"].append(cond)

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    forecast = []
    for date_str in sorted(by_day.keys())[:5]:
        bucket = by_day[date_str]
        if not bucket["highs"] or not bucket["lows"]:
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            day = day_names[dt.weekday()]
        except Exception:
            day = date_str[5:]
        dominant_cond = Counter(bucket["conds"]).most_common(1)[0][0] if bucket["conds"] else ""
        forecast.append({
            "day": day,
            "date": date_str,
            "high": round(max(bucket["highs"])),
            "low": round(min(bucket["lows"])),
            "condition": dominant_cond,
        })

    return {"forecast": forecast, "city": data.get("city", {}).get("name", city_name)}


def get_weather_by_city(city_name):
    """
    Fetches the current weather and forecast for a specific city via OpenWeatherMap.
    """
    api_key = os.environ.get("OPENWEATHERMAP_API_KEY", "")
    if not api_key:
        return {"error": "API Key missing for OpenWeatherMap"}
        
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={api_key}&units=metric"
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 404:
            return {"error": "City not found"}
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}
