# IoT Weather Station

An indoor/outdoor weather monitor built on the M5Stack Core2 with a cloud backend, voice assistant, and Streamlit dashboard. Built for the **Cloud and Advanced Analytics** course (HEC Lausanne, 2026).

> **Demo video:** <https://youtu.be/gWAKfFcbrfg>
> **Live dashboard:** <https://weather-dashboard-1087371609781.europe-west6.run.app>
> **Backend API:** <https://weather-backend-1087371609781.europe-west6.run.app>

---

## Author

**Ismael Ouarit** — solo project. Designed and built the entire stack: M5Stack Core2 firmware (sensors, touch UI, voice pipeline, WiFi captive portal, motion-triggered announcements), Flask backend on Cloud Run (BigQuery integration, OpenWeatherMap, Google Speech-to-Text and Text-to-Speech, Gemini 2.5 Flash), and the Streamlit dashboard on Cloud Run.

---

## What it does

The M5Stack sits on your desk and quietly logs what's going on in your room: temperature, humidity, and the kind of air you're actually breathing (TVOC and eCO2 from an SGP30), once a minute, every minute. It pairs that with live outdoor conditions and a 5-day forecast from OpenWeatherMap for wherever you are, either auto-detected from your IP or picked from a city dropdown. Everything streams into BigQuery so the dashboard can show you patterns over days, weeks, or longer.

Hold the middle button and talk to it. _"What was the humidity yesterday?"_ _"Do I need an umbrella tomorrow?"_ _"What's the weather in Paris?"_ Your voice goes to Google Speech-to-Text, the transcript gets handed to Gemini 2.5 Flash along with whatever sensor history and forecast data the question needs, and the answer comes back as actual speech through the Core2 speaker. The whole round-trip takes about three seconds.

Walk into the room and the PIR sensor catches you. If something useful is happening, like rain on the way, air that's gone stale, or indoor temperature creeping up, the device speaks up. But only once every ten minutes, because nobody wants to be lectured by their weather station.

When humidity drops below 40% or air quality goes bad, the onboard RGB LED changes color and an alert flags the screen. You don't have to be looking at the device to know something's off.

The Streamlit dashboard gives you the same data on a bigger screen: current conditions, trends over time, air quality breakdowns, the outdoor forecast, and day-to-day statistics.

And the whole thing is built to survive real-world conditions. Pull the plug and plug it back in: the device pulls its last reading from BigQuery so you're not staring at a blank screen during boot. Move to a different WiFi network: change the SSID and password directly on the device through a captive portal, no reflashing or laptop required. The backend even broadcasts itself on the LAN so the device can find it without any hardcoded IPs.

---

## Architecture (3-tier)

```
┌─────────────────────┐      ┌──────────────────────┐      ┌────────────────────┐
│   M5Stack Core2     │      │  Flask API           │      │  BigQuery          │
│   (MicroPython)     │◄────►│  (Cloud Run)         │◄────►│  weather_station   │
│                     │ HTTP │                      │      │  dataset           │
│ • SHT30 (T/H)       │      │ • Sensor ingest      │      └────────────────────┘
│ • SGP30 (air)       │ +UDP │ • Voice pipeline     │                 ▲
│ • PIR (motion)      │ disc │ • Weather + forecast │                 │
│ • Touch UI (8 scr.) │      │ • Announcements      │                 │
│ • Mic / speaker     │      │                      │                 │  reads
│ • RGB alerts        │      └──────────────────────┘                 │
└─────────────────────┘                ▲                   ┌──────────┴───────────┐
                                       │ HTTP              │  Streamlit Dashboard │
                                       ▼                   │  (Cloud Run)         │
                              ┌────────────────────┐       └──────────────────────┘
                              │  External APIs     │                 ▲
                              │  • OpenWeatherMap  │◄──── HTTP ──────┘
                              │  • Google STT/TTS  │     (live weather)
                              │  • Gemini 2.5      │
                              └────────────────────┘
```

The dashboard reads BigQuery directly and hits OpenWeatherMap for live conditions; it never calls the Flask backend or talks to the device. UDP discovery lives between the device and the backend on a LAN deployment (the device broadcasts to find the backend's IP) and is unused on Cloud Run, where the backend has a stable URL.

---

## Repository structure

```
.
├── backend-api/            Flask middleware (Cloud Run)
│   ├── app.py                  HTTP routes + UDP discovery server
│   ├── bq_client.py            BigQuery read/write
│   ├── weather_client.py       OpenWeatherMap wrapper
│   ├── voice_assistant.py      STT → Gemini → TTS pipeline
│   ├── announcement_service.py Motion-triggered weather rundowns
│   ├── Dockerfile              Pinned Python 3.12 + gunicorn entrypoint
│   └── requirements.txt
│
├── dashboard/              Streamlit web dashboard (Cloud Run)
│   ├── app.py                  Multi-page UI backed by BigQuery
│   ├── weather_client.py       Local copy of the OWM wrapper
│   ├── .streamlit/config.toml  Theme
│   ├── Dockerfile              Pinned Python 3.12 + streamlit entrypoint
│   └── requirements.txt
│
├── m5stack-device/         MicroPython firmware for M5Stack Core2
│   ├── uiflow_combined.py      Main firmware: 8 screens, sensors, voice
│   ├── wifi_manager.py         Captive portal for WiFi changes
│   └── test_*.py               Standalone hardware diagnostics
│
├── .env.example            Template for required environment variables
└── README.md
```

---

## Setup & Deployment

### 0. Prerequisites
- Google Cloud project with billing enabled and the following APIs activated:
  BigQuery, Cloud Run, Cloud Build, Speech-to-Text, Text-to-Speech, Generative Language (Gemini).
- A service account with `BigQuery Data Editor`, `BigQuery Job User`, and the relevant speech/AI permissions. Download its JSON key.
- An **OpenWeatherMap** API key (free tier is enough).
- An **M5Stack Core2** with ENVIII (SHT30), TVOC/eCO2 (SGP30), and PIR units.

### 1. BigQuery setup
Create a dataset called `weather_station` with two tables:

| Table | Columns |
|---|---|
| `sensor_data` | `timestamp TIMESTAMP`, `temperature FLOAT`, `humidity FLOAT`, `tvoc INT64`, `eco2 INT64` |
| `weather_data` | `timestamp TIMESTAMP`, `temperature FLOAT`, `outdoor_humidity FLOAT`, `wind_speed FLOAT`, `weather_condition STRING` |

### 2. Environment variables

Copy `.env.example` to `.env` (kept out of git) and fill in:

```env
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
BQ_DATASET_NAME=weather_station

OPENWEATHERMAP_API_KEY=...
GEMINI_API_KEY=...
```

### 3. Deploy the Flask backend to Cloud Run

```bash
cd backend-api
gcloud run deploy weather-backend \
  --source . \
  --region europe-west6 \
  --allow-unauthenticated \
  --set-env-vars "BQ_DATASET_NAME=weather_station,OPENWEATHERMAP_API_KEY=...,GEMINI_API_KEY=..."
```

### 4. Deploy the Streamlit dashboard to Cloud Run

```bash
cd dashboard
gcloud run deploy weather-dashboard \
  --source . \
  --region europe-west6 \
  --allow-unauthenticated \
  --set-env-vars "BQ_DATASET_NAME=weather_station,OPENWEATHERMAP_API_KEY=..."
```

### 5. Flash the M5Stack

1. Open [UIFlow](https://flow.m5stack.com/) and connect the Core2.
2. Upload [`m5stack-device/uiflow_combined.py`](m5stack-device/uiflow_combined.py) and [`m5stack-device/wifi_manager.py`](m5stack-device/wifi_manager.py) to `/flash/`.
3. Set `uiflow_combined.py` as the boot script.
4. On first boot the device joins `M5Weather-Setup`; connect any phone/laptop and open `http://192.168.4.1` to enter WiFi credentials. The same flow can be re-triggered at any time from the **Network** screen.

### 6. Running locally (optional, for development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend-api/requirements.txt
pip install -r dashboard/requirements.txt

# Backend
cd backend-api && python app.py

# Dashboard
cd dashboard && streamlit run app.py
```

---

## Features mapped to the rubric

| Requirement | Where it lives |
|---|---|
| BigQuery storage | [backend-api/bq_client.py](backend-api/bq_client.py) |
| Indoor T/H + air quality + motion | [m5stack-device/uiflow_combined.py](m5stack-device/uiflow_combined.py) — `read_sht30`, `read_sgp30`, `read_pir` |
| Time/date via NTP | `sync_ntp()` in [uiflow_combined.py](m5stack-device/uiflow_combined.py) |
| Outdoor weather + 5-day forecast | [backend-api/weather_client.py](backend-api/weather_client.py) |
| Alerts (humidity, air quality) | `gen_alerts()` in [uiflow_combined.py](m5stack-device/uiflow_combined.py) |
| Speech-to-text / Text-to-speech | [backend-api/voice_assistant.py](backend-api/voice_assistant.py) |
| LLM-generated answers | Gemini 2.5 Flash, [voice_assistant.py](backend-api/voice_assistant.py) |
| Motion-triggered announcements (rate-limited) | [backend-api/announcement_service.py](backend-api/announcement_service.py) |
| Boot-time BigQuery sync | `get_latest_bq()` in [uiflow_combined.py](m5stack-device/uiflow_combined.py) |
| WiFi reconfiguration on-device | [m5stack-device/wifi_manager.py](m5stack-device/wifi_manager.py) — captive portal |
| Resilience to network loss | Lazy API resolution, cached host file, UDP discovery, fallback IPs |
| Historical dashboard | [dashboard/app.py](dashboard/app.py) |

---

## Security note

No credentials are committed. `.env`, GCP service-account JSON, and any `*-key.json` files are excluded via [`.gitignore`](.gitignore). Always rotate keys after rotating contributors or if a key has been exposed.

---

## License

MIT — see [`LICENSE`](LICENSE).
