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


