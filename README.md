# M5Stack Weather Station

This project implements an indoor/outdoor weather monitor with an M5Stack Core2 device, Google Cloud (Run & BigQuery), and a Streamlit dashboard.

## Architecture
- **M5Stack Device**: Collects indoor telemetry (Temp, Humidity, Air Quality, Motion). Displays data and interacts with users via voice.
- **Middleware (Flask)**: Deployed on Google Cloud Run. Bridges the M5Stack UI with the database, and accesses external APIs (OpenWeatherMap, Google Cloud/OpenAI).
- **Dashboard (Streamlit)**: Deployed on Google Cloud Run. Displays current and historical data from BigQuery in a polished UI.

## Getting Started
Please see the individual directories for details on how to deploy or run each component:
- `backend-api/`: Flask application deployment.
- `dashboard/`: Streamlit dashboard deployment.
- `m5stack-device/`: Firmware loading and setup.

## Deployment Variables
The system relies on various abstracted variables across components. 
Check `.env.example` to see required configuration properties.
