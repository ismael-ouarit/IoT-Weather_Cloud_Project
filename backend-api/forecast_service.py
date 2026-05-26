"""
SARIMA-based weather forecast service.

Uses Seasonal ARIMA (SARIMA) to predict future temperature and humidity
based on historical data stored in BigQuery.
"""

import pandas as pd
import numpy as np
from statsmodels.tsa.statespace.sarimax import SARIMAX
from datetime import datetime, timedelta
import warnings

warnings.filterwarnings("ignore")


def prepare_time_series(records, value_column="temperature"):
    """
    Converts raw BigQuery records into a pandas Series indexed by timestamp.
    
    Args:
        records: List of dicts with 'timestamp' and the target value column.
        value_column: The column to forecast (e.g. 'temperature', 'humidity').
    
    Returns:
        A pandas Series with DatetimeIndex, resampled to hourly frequency.
    """
    if not records:
        return pd.Series(dtype=float)

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")
    df = df.set_index("timestamp")

    # Resample to hourly, forward-fill small gaps
    series = df[value_column].resample("h").mean().ffill()
    return series


def fit_sarima(series, order=(1, 1, 1), seasonal_order=(1, 1, 1, 24)):
    """
    Fits a SARIMA model on the given time series.

    Default seasonal_order uses a period of 24 (hourly data with daily seasonality).
    For daily data, use seasonal_order=(1, 1, 1, 7) for weekly seasonality.

    Args:
        series: pandas Series with DatetimeIndex.
        order: (p, d, q) — non-seasonal ARIMA parameters.
        seasonal_order: (P, D, Q, s) — seasonal ARIMA parameters.

    Returns:
        Fitted SARIMAX model results.
    """
    model = SARIMAX(
        series,
        order=order,
        seasonal_order=seasonal_order,
        enforce_stationarity=False,
        enforce_invertibility=False,
    )
    results = model.fit(disp=False, maxiter=200)
    return results


def forecast(series, steps=72, order=(1, 1, 1), seasonal_order=(1, 1, 1, 24)):
    """
    Generates a forecast from a fitted SARIMA model.

    Args:
        series: pandas Series with DatetimeIndex (historical observations).
        steps: Number of future time steps to predict (default 72 = 3 days hourly).
        order: ARIMA order.
        seasonal_order: Seasonal ARIMA order.

    Returns:
        dict with 'timestamps', 'predicted', 'lower_bound', 'upper_bound' lists.
    """
    if len(series) < 48:
        raise ValueError(
            f"Need at least 48 data points for SARIMA, got {len(series)}. "
            "Collect more historical data before forecasting."
        )

    results = fit_sarima(series, order=order, seasonal_order=seasonal_order)

    # Produce forecast with 95% confidence interval
    forecast_result = results.get_forecast(steps=steps)
    predicted = forecast_result.predicted_mean
    confidence = forecast_result.conf_int(alpha=0.05)

    timestamps = [t.isoformat() for t in predicted.index]
    values = [round(v, 2) for v in predicted.values]
    lower = [round(v, 2) for v in confidence.iloc[:, 0].values]
    upper = [round(v, 2) for v in confidence.iloc[:, 1].values]

    return {
        "timestamps": timestamps,
        "predicted": values,
        "lower_bound": lower,
        "upper_bound": upper,
        # Zipped record form — what the M5Stack device consumes.
        "predictions": [{"timestamp": t, "value": v} for t, v in zip(timestamps, values)],
    }


def generate_mock_history(days=14):
    """
    Produces mock hourly temperature & humidity data for testing
    when BigQuery history is not yet available.
    """
    np.random.seed(42)
    hours = days * 24
    timestamps = [
        datetime.now() - timedelta(hours=hours - i) for i in range(hours)
    ]

    # Simulate daily temperature cycle: base 18°C, amplitude 6°C, peak at 14:00
    base_temp = 18
    amplitude = 6
    temps = []
    for t in timestamps:
        hour_effect = amplitude * np.sin(np.pi * (t.hour - 8) / 12)
        noise = np.random.normal(0, 0.5)
        temps.append(round(base_temp + hour_effect + noise, 1))

    # Simulate humidity inversely correlated with temperature
    humidities = [round(max(30, min(90, 70 - (t - base_temp) * 2 + np.random.normal(0, 2))), 1) for t in temps]

    records = [
        {"timestamp": ts.isoformat(), "temperature": temp, "humidity": hum}
        for ts, temp, hum in zip(timestamps, temps, humidities)
    ]
    return records


def get_weather_forecast(records=None, metric="temperature", forecast_hours=72):
    """
    High-level entry point: takes historical records, returns a forecast dict.

    Args:
        records: List of dicts from BigQuery. If None, uses mock data.
        metric: 'temperature' or 'humidity'.
        forecast_hours: How many hours ahead to predict.

    Returns:
        dict with forecast data and model diagnostics.
    """
    if records is None:
        records = generate_mock_history(days=14)

    series = prepare_time_series(records, value_column=metric)

    if series.empty:
        return {"error": "No data available for forecasting"}

    try:
        result = forecast(series, steps=forecast_hours)
        result["metric"] = metric
        result["model"] = "SARIMA(1,1,1)(1,1,1,24)"
        result["history_points"] = len(series)
        result["last_observation"] = {
            "timestamp": series.index[-1].isoformat(),
            "value": round(series.iloc[-1], 2),
        }
        return result
    except Exception as e:
        return {"error": str(e)}
