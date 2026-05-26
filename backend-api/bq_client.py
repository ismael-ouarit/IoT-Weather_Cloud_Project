from google.cloud import bigquery
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

DATASET = os.environ.get("BQ_DATASET_NAME", "weather_station")


def get_bq_client():
    # Implicitly uses GOOGLE_APPLICATION_CREDENTIALS
    return bigquery.Client()


def _table_id():
    """Returns the fully-qualified table ID for sensor_data."""
    client = get_bq_client()
    return f"{client.project}.{DATASET}.sensor_data"


def insert_sensor_data(data):
    """
    Inserts a row of sensor data into BigQuery.
    Example data dict: {"temperature": 22.5, "humidity": 45.0, "tvoc": 50, "eco2": 400, "timestamp": "2023-10-01T12:00:00Z"}
    """
    try:
        client = get_bq_client()
        table_id = _table_id()

        # Ensure a timestamp is present
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow().isoformat()

        client.insert_rows_json(table_id, [data])
        print(f"Inserted {data} into {table_id}")
    except Exception as e:
        print(f"Error submitting to BigQuery: {e}")


def insert_weather_data(weather_api_response):
    """
    Inserts a row into the weather_data table from a raw OpenWeatherMap response dict.
    """
    try:
        client = get_bq_client()
        table_id = f"{client.project}.{DATASET}.weather_data"
        row = {
            "timestamp":         datetime.utcnow().isoformat(),
            "temperature":       weather_api_response.get("main", {}).get("temp"),
            "outdoor_humidity":  weather_api_response.get("main", {}).get("humidity"),
            "wind_speed":        weather_api_response.get("wind", {}).get("speed"),
            "weather_condition": weather_api_response.get("weather", [{}])[0].get("main"),
        }
        client.insert_rows_json(table_id, [row])
        print(f"[BQ] weather_data inserted: {row}")
    except Exception as e:
        print(f"[BQ] Error inserting weather_data: {e}")


def get_historical_data(hours=24):
    """
    Fetches historical sensor data from BigQuery for the last N hours.
    Returns a list of dicts with timestamp, temperature, humidity, tvoc, eco2.
    """
    try:
        client = get_bq_client()
        table_id = _table_id()
        query = f"""
            SELECT timestamp, temperature, humidity, tvoc, eco2
            FROM `{table_id}`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(hours)} HOUR)
            ORDER BY timestamp ASC
        """
        results = client.query(query).result()
        rows = []
        for row in results:
            rows.append({
                "timestamp": row.timestamp.isoformat() if hasattr(row.timestamp, 'isoformat') else str(row.timestamp),
                "temperature": float(row.temperature) if row.temperature is not None else None,
                "humidity": float(row.humidity) if row.humidity is not None else None,
                "tvoc": int(row.tvoc) if row.tvoc is not None else None,
                "eco2": int(row.eco2) if row.eco2 is not None else None,
            })
        return rows
    except Exception as e:
        print(f"Error fetching historical data: {e}")
        return []


def get_latest_reading():
    """
    Returns the most recent sensor data row from BigQuery.
    """
    try:
        client = get_bq_client()
        table_id = _table_id()
        query = f"""
            SELECT timestamp, temperature, humidity, tvoc, eco2
            FROM `{table_id}`
            ORDER BY timestamp DESC
            LIMIT 1
        """
        results = client.query(query).result()
        for row in results:
            return {
                "timestamp": row.timestamp.isoformat() if hasattr(row.timestamp, 'isoformat') else str(row.timestamp),
                "temperature": float(row.temperature) if row.temperature is not None else None,
                "humidity": float(row.humidity) if row.humidity is not None else None,
                "tvoc": int(row.tvoc) if row.tvoc is not None else None,
                "eco2": int(row.eco2) if row.eco2 is not None else None,
            }
        return None
    except Exception as e:
        print(f"Error fetching latest reading: {e}")
        return None


def get_sensor_data_for_date(date_str):
    """
    Returns all sensor readings for a specific date (format: 'YYYY-MM-DD').
    Includes aggregated stats (min, max, avg).
    """
    try:
        client = get_bq_client()
        table_id = _table_id()
        query = f"""
            SELECT timestamp, temperature, humidity, tvoc, eco2
            FROM `{table_id}`
            WHERE DATE(timestamp) = DATE('{date_str}')
            ORDER BY timestamp ASC
        """
        results = client.query(query).result()
        rows = []
        for row in results:
            rows.append({
                "timestamp": row.timestamp.isoformat() if hasattr(row.timestamp, 'isoformat') else str(row.timestamp),
                "temperature": float(row.temperature) if row.temperature is not None else None,
                "humidity": float(row.humidity) if row.humidity is not None else None,
                "tvoc": int(row.tvoc) if row.tvoc is not None else None,
                "eco2": int(row.eco2) if row.eco2 is not None else None,
            })
        return rows
    except Exception as e:
        print(f"Error fetching data for date {date_str}: {e}")
        return []


def get_sensor_stats_for_date(date_str):
    """
    Returns aggregated statistics (min, max, avg) for a given date.
    """
    try:
        client = get_bq_client()
        table_id = _table_id()
        query = f"""
            SELECT
                MIN(temperature) AS min_temp,
                MAX(temperature) AS max_temp,
                AVG(temperature) AS avg_temp,
                MIN(humidity) AS min_hum,
                MAX(humidity) AS max_hum,
                AVG(humidity) AS avg_hum,
                AVG(tvoc) AS avg_tvoc,
                AVG(eco2) AS avg_eco2,
                COUNT(*) AS reading_count
            FROM `{table_id}`
            WHERE DATE(timestamp) = DATE('{date_str}')
        """
        results = client.query(query).result()
        for row in results:
            if row.reading_count == 0:
                return None
            return {
                "date": date_str,
                "temperature": {
                    "min": round(float(row.min_temp), 1) if row.min_temp else None,
                    "max": round(float(row.max_temp), 1) if row.max_temp else None,
                    "avg": round(float(row.avg_temp), 1) if row.avg_temp else None,
                },
                "humidity": {
                    "min": round(float(row.min_hum), 1) if row.min_hum else None,
                    "max": round(float(row.max_hum), 1) if row.max_hum else None,
                    "avg": round(float(row.avg_hum), 1) if row.avg_hum else None,
                },
                "avg_tvoc": round(float(row.avg_tvoc), 0) if row.avg_tvoc else None,
                "avg_eco2": round(float(row.avg_eco2), 0) if row.avg_eco2 else None,
                "reading_count": row.reading_count,
            }
        return None
    except Exception as e:
        print(f"Error fetching stats for date {date_str}: {e}")
        return None


def check_threshold(metric, threshold, date_str=None, direction="above"):
    """
    Checks if a given metric exceeded (or fell below) a threshold.

    Args:
        metric: 'temperature', 'humidity', 'tvoc', or 'eco2'
        threshold: numeric threshold value
        date_str: date to check (YYYY-MM-DD). If None, checks last 24 hours.
        direction: 'above' or 'below'

    Returns:
        dict with 'exceeded': bool, 'count': number of readings that crossed,
        'peak_value': the most extreme value, 'peak_time': when it occurred.
    """
    try:
        client = get_bq_client()
        table_id = _table_id()

        comparator = ">" if direction == "above" else "<"
        order = "DESC" if direction == "above" else "ASC"

        if date_str:
            date_filter = f"DATE(timestamp) = DATE('{date_str}')"
        else:
            date_filter = "timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)"

        query = f"""
            SELECT timestamp, {metric}
            FROM `{table_id}`
            WHERE {date_filter} AND {metric} {comparator} {threshold}
            ORDER BY {metric} {order}
        """
        results = list(client.query(query).result())

        if not results:
            return {
                "exceeded": False,
                "count": 0,
                "peak_value": None,
                "peak_time": None,
                "metric": metric,
                "threshold": threshold,
                "direction": direction,
            }

        peak_row = results[0]
        return {
            "exceeded": True,
            "count": len(results),
            "peak_value": float(getattr(peak_row, metric)),
            "peak_time": peak_row.timestamp.isoformat() if hasattr(peak_row.timestamp, 'isoformat') else str(peak_row.timestamp),
            "metric": metric,
            "threshold": threshold,
            "direction": direction,
        }
    except Exception as e:
        print(f"Error checking threshold: {e}")
        return {"exceeded": False, "error": str(e)}
