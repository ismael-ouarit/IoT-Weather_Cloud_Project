"""BigQuery loader — reads service account JSON, returns plain dicts/lists."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import dotenv_values

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_DIR = _PROJECT_ROOT / "backend-api"
_ENV = dotenv_values(_ENV_DIR / ".env") or {}


def _resolve_credentials_path() -> str:
    raw = (_ENV.get("GOOGLE_APPLICATION_CREDENTIALS")
           or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
           or "").strip().strip('"').strip("'")
    if raw:
        p = Path(raw)
        if not p.is_absolute():
            p = _ENV_DIR / raw
        if p.exists():
            return str(p)
    for candidate in list(_PROJECT_ROOT.glob("*.json")) + list(_ENV_DIR.glob("*.json")):
        try:
            with open(candidate) as f:
                if json.load(f).get("type") == "service_account":
                    return str(candidate)
        except Exception:
            continue
    return ""


CREDS_PATH = _resolve_credentials_path()
DATASET = os.environ.get("BQ_DATASET_NAME", "weather_station")

_client = None


def get_client():
    global _client
    if _client is None:
        from google.cloud import bigquery
        from google.oauth2 import service_account
        with open(CREDS_PATH) as f:
            info = json.load(f)
        creds = service_account.Credentials.from_service_account_info(info)
        _client = bigquery.Client(project=info.get("project_id"), credentials=creds)
    return _client


COND_ICON = {
    "clear": "☀️", "clouds": "☁️", "rain": "🌧️", "drizzle": "🌦️",
    "thunderstorm": "⛈️", "snow": "❄️", "mist": "🌫️",
    "fog": "🌫️", "haze": "🌫️",
}


def _icon_for(condition: str) -> str:
    c = (condition or "").lower()
    return next((v for k, v in COND_ICON.items() if k in c), "🌤️")


def load_overview(hours: int = 24) -> dict:
    """Returns all data needed by the Overview page as a flat dict."""
    if not CREDS_PATH:
        return _empty()

    try:
        client = get_client()
        project = client.project

        sensor_df = client.query(f"""
            SELECT timestamp, temperature, humidity, tvoc, eco2
            FROM `{project}.{DATASET}.sensor_data`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
            ORDER BY timestamp ASC
        """).to_dataframe()

        weather_df = client.query(f"""
            SELECT timestamp, temperature, outdoor_humidity, wind_speed, weather_condition
            FROM `{project}.{DATASET}.weather_data`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
            ORDER BY timestamp ASC
        """).to_dataframe()
    except Exception as e:
        print(f"[bq] query failed: {e}")
        return _empty()

    out = _empty()
    if not sensor_df.empty:
        latest = sensor_df.iloc[-1]
        out["indoor_temp"] = float(latest["temperature"])
        out["indoor_humidity"] = float(latest["humidity"])
        out["tvoc"] = float(latest["tvoc"])
        out["eco2"] = float(latest["eco2"])

        # today range
        import pandas as pd
        sensor_df["ts"] = pd.to_datetime(sensor_df["timestamp"], utc=True)
        today = datetime.now(timezone.utc).date()
        today_df = sensor_df[sensor_df["ts"].dt.date == today]
        if not today_df.empty:
            out["high_today"] = float(today_df["temperature"].max())
            out["low_today"] = float(today_df["temperature"].min())

        # last 7 readings
        recent = sensor_df.tail(7)
        out["recent"] = [
            {
                "time": r["ts"].strftime("%H:%M"),
                "temp": round(float(r["temperature"]), 1),
            }
            for _, r in recent.iterrows()
        ]

    if not weather_df.empty:
        wlatest = weather_df.iloc[-1]
        out["outdoor_temp"] = float(wlatest["temperature"])
        out["outdoor_humidity"] = float(wlatest["outdoor_humidity"])
        out["wind_speed"] = float(wlatest["wind_speed"])
        out["weather_condition"] = (wlatest["weather_condition"] or "").capitalize()
        out["weather_icon"] = _icon_for(wlatest["weather_condition"])

    # build alerts
    alerts = []
    if out["indoor_temp"] and out["indoor_temp"] > 30:
        alerts.append({"icon": "🌡️", "label": "High indoor temp", "value": f"{out['indoor_temp']:.1f} °C"})
    if out["indoor_humidity"] and out["indoor_humidity"] < 40:
        alerts.append({"icon": "💧", "label": "Low humidity", "value": f"{out['indoor_humidity']:.0f} %"})
    if out["tvoc"] and out["tvoc"] >= 220:
        alerts.append({"icon": "🌿", "label": "Poor air quality", "value": f"{out['tvoc']:.0f} ppb"})
    if out["eco2"] and out["eco2"] >= 1000:
        alerts.append({"icon": "💨", "label": "High eCO₂", "value": f"{out['eco2']:.0f} ppm"})
    out["alerts"] = alerts

    out["updated_at"] = datetime.now(timezone.utc).strftime("%d %b · %H:%M UTC")
    out["day"] = datetime.now().strftime("%A")
    out["date"] = datetime.now().strftime("%d %b, %Y")
    return out


def _empty() -> dict:
    return {
        "indoor_temp": 0.0, "indoor_humidity": 0.0, "tvoc": 0.0, "eco2": 0.0,
        "outdoor_temp": 0.0, "outdoor_humidity": 0.0, "wind_speed": 0.0,
        "weather_condition": "—", "weather_icon": "🌤️",
        "high_today": 0.0, "low_today": 0.0,
        "recent": [], "alerts": [],
        "updated_at": "", "day": "", "date": "",
    }
