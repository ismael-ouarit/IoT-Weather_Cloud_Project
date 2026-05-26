"""SkySense — Weather Station Dashboard"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import dotenv_values
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_DIR = _PROJECT_ROOT / "backend-api"
_ENV = dotenv_values(_ENV_DIR / ".env") or {}
for _k, _v in _ENV.items():
    if _v:
        os.environ[_k] = _v

# Make backend-api modules importable (weather_client, etc.)
if str(_ENV_DIR) not in sys.path:
    sys.path.insert(0, str(_ENV_DIR))


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
            import json as _json
            with open(candidate) as f:
                if _json.load(f).get("type") == "service_account":
                    return str(candidate)
        except Exception:
            continue
    return ""


_CREDS_PATH = _resolve_credentials_path()
if _CREDS_PATH:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _CREDS_PATH

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google.cloud import bigquery
from streamlit_option_menu import option_menu

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SkySense · Weather Station",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme / CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">

<style>
/* ── Globals ─────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    -webkit-font-smoothing: antialiased;
}

#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none !important; }
/* Keep header visible (so the sidebar expand button renders) but transparent */
header[data-testid="stHeader"],
.stAppHeader {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    height: auto !important;
    visibility: visible !important;
}
[data-testid="stToolbar"] { background: transparent !important; }

.stApp {
    background:
        radial-gradient(ellipse 800px 600px at 100% 0%, rgba(140, 90, 255, 0.08), transparent 50%),
        radial-gradient(ellipse 600px 400px at 0% 100%, rgba(70, 130, 255, 0.05), transparent 50%),
        linear-gradient(180deg, #0A0E1A 0%, #0E1525 100%);
}

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }

.block-container {
    padding-top: 4.5rem !important;
    padding-bottom: 2rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    max-width: 100% !important;
}

/* ── Sidebar ─────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: rgba(8, 12, 24, 0.38);
    backdrop-filter: blur(52px) saturate(210%) brightness(0.92);
    -webkit-backdrop-filter: blur(52px) saturate(210%) brightness(0.92);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 20px;
    margin: 0.75rem 0 0.75rem 0.75rem;
    padding-top: 1rem !important;
}

section[data-testid="stSidebar"] > div { padding-top: 0 !important; }

section[data-testid="stSidebar"] iframe {
    border-radius: 20px !important;
    overflow: hidden !important;
}

/* Sidebar re-open button — Streamlit 1.57 testid is stExpandSidebarButton.
   It lives inside the header which is now visible (just transparent), so the
   button renders at its natural top-left position. Style it to a clearly
   visible white pill. */
button[data-testid="stExpandSidebarButton"],
[data-testid="stExpandSidebarButton"] {
    background: #0A0E1A !important;
    border-radius: 12px !important;
    padding: 0.5rem 0.7rem !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5) !important;
    cursor: pointer !important;
    transition: transform 0.2s ease, background 0.2s ease !important;
    opacity: 1 !important;
    visibility: visible !important;
}
button[data-testid="stExpandSidebarButton"] svg,
button[data-testid="stExpandSidebarButton"] path,
[data-testid="stExpandSidebarButton"] svg,
[data-testid="stExpandSidebarButton"] path {
    fill: #FFFFFF !important;
    color: #FFFFFF !important;
    stroke: #FFFFFF !important;
    opacity: 1 !important;
}
button[data-testid="stExpandSidebarButton"]:hover,
[data-testid="stExpandSidebarButton"]:hover {
    transform: scale(1.05) !important;
    background: #0E1525 !important;
}

/* option_menu pills */
.nav-link {
    transition: all 0.2s ease !important;
    margin: 4px 0 !important;
}
.nav-link:hover {
    background: rgba(255,255,255,0.04) !important;
    transform: translateX(2px);
}
.nav-link-selected {
    background: linear-gradient(135deg, rgba(140, 90, 255, 0.25) 0%, rgba(98, 87, 255, 0.15) 100%) !important;
    box-shadow: 0 0 0 1px rgba(140, 90, 255, 0.3), inset 0 1px 0 rgba(255,255,255,0.05);
}

/* Sidebar slider — track */
section[data-testid="stSidebar"] [data-testid="stSlider"] > div > div > div > div {
    background: linear-gradient(90deg, #8C5AFF 0%, #4A8FFF 100%) !important;
    height: 5px !important;
    border-radius: 5px !important;
}

/* Thumb — matches track height */
section[data-testid="stSidebar"] [data-testid="stSlider"] [role="slider"] {
    width: 5px !important;
    height: 5px !important;
    border-radius: 50% !important;
    background: #FFFFFF !important;
    border: none !important;
    box-shadow: 0 0 0 2px rgba(255,255,255,0.9) !important;
    cursor: grab !important;
    outline: none !important;
}
section[data-testid="stSidebar"] [data-testid="stSlider"] [role="slider"]:focus,
section[data-testid="stSidebar"] [data-testid="stSlider"] [role="slider"]:active {
    box-shadow: 0 0 0 3px rgba(140, 90, 255, 0.6) !important;
    cursor: grabbing !important;
}

/* Value bubble above thumb */
section[data-testid="stSidebar"] [data-testid="stSliderThumbValue"] {
    background: rgba(12, 16, 34, 0.9) !important;
    backdrop-filter: blur(8px) !important;
    -webkit-backdrop-filter: blur(8px) !important;
    border: 1px solid rgba(140, 90, 255, 0.35) !important;
    border-radius: 6px !important;
    color: #FFFFFF !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.65rem !important;
    padding: 0.15rem 0.4rem !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important;
    white-space: nowrap !important;
    margin-bottom: 22px !important;
    transform: translateY(-14px) !important;
}

/* Hide tick bar for a cleaner look */
section[data-testid="stSidebar"] [data-testid="stSliderTickBar"] {
    display: none !important;
}

/* Refresh button */
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(140, 90, 255, 0.22) !important;
    color: #C9B6FF !important;
    border: 1px solid rgba(140, 90, 255, 0.40) !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(140, 90, 255, 0.32) !important;
    border-color: rgba(140, 90, 255, 0.6) !important;
    transform: translateY(-1px);
}

/* ── Cards (st.container border=True) ────────────────────────────────── */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255, 255, 255, 0.04) !important;
    backdrop-filter: blur(24px) saturate(160%) !important;
    -webkit-backdrop-filter: blur(24px) saturate(160%) !important;
    border-radius: 20px !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    padding: 1.4rem !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.08);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    transform: translateY(-2px);
    background: rgba(255, 255, 255, 0.06) !important;
    box-shadow: 0 12px 40px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.12);
}

/* ── Metric cards ────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: rgba(255, 255, 255, 0.04);
    backdrop-filter: blur(24px) saturate(160%);
    -webkit-backdrop-filter: blur(24px) saturate(160%);
    padding: 1.2rem 1.3rem;
    border-radius: 16px;
    border: 1px solid rgba(255,255,255,0.10);
    box-shadow: 0 4px 16px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.08);
    transition: transform 0.2s ease;
}
[data-testid="stMetric"]:hover { transform: translateY(-2px); }
[data-testid="stMetricLabel"] {
    color: #8899AA !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="stMetricValue"] {
    color: #FFFFFF !important;
    font-size: 1.9rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em;
}

/* ── Hero card ───────────────────────────────────────────────────────── */
.hero-card {
    background:
        radial-gradient(ellipse 400px 200px at 100% 0%, rgba(255, 200, 100, 0.10), transparent),
        rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(32px) saturate(180%);
    -webkit-backdrop-filter: blur(32px) saturate(180%);
    border-radius: 24px;
    padding: 2rem 2.2rem;
    border: 1px solid rgba(255,255,255,0.12);
    box-shadow: 0 12px 40px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.12);
    position: relative;
    overflow: hidden;
    min-height: 280px;
}
.hero-card::before {
    content: "";
    position: absolute; top: -50%; right: -20%;
    width: 400px; height: 400px;
    background: radial-gradient(circle, rgba(140, 90, 255, 0.15) 0%, transparent 70%);
    pointer-events: none;
}
.hero-loc {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: rgba(140, 90, 255, 0.2);
    color: #D4C4FF;
    padding: 0.4rem 1rem;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
    border: 1px solid rgba(140, 90, 255, 0.25);
}
.hero-day { font-size: 2.4rem; font-weight: 800; color: #FFFFFF; margin: 1rem 0 0.2rem; letter-spacing: -0.03em; }
.hero-date { font-size: 0.95rem; color: #8899AA; margin-bottom: 1.5rem; font-weight: 500; }
.hero-temp {
    font-size: 5.5rem; font-weight: 800; color: #FFFFFF; line-height: 1; letter-spacing: -0.05em;
    background: linear-gradient(180deg, #FFFFFF 0%, #C9B6FF 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}
.hero-range { color: #8899AA; font-size: 0.9rem; margin-top: 0.5rem; font-weight: 500; }
.hero-cond { font-size: 1.7rem; font-weight: 700; color: #FFFFFF; text-align: right; letter-spacing: -0.02em; }
.hero-feels { color: #8899AA; font-size: 0.95rem; text-align: right; margin-top: 0.4rem; font-weight: 500; }
.hero-icon { font-size: 7rem; text-align: right; line-height: 1; filter: drop-shadow(0 8px 24px rgba(255, 200, 100, 0.2)); }

/* ── Hour cards ──────────────────────────────────────────────────────── */
.hour-card {
    background: rgba(255, 255, 255, 0.04);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border-radius: 16px;
    padding: 1rem 0.5rem;
    text-align: center;
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
    transition: all 0.2s ease;
    cursor: default;
}
.hour-card:hover {
    background: rgba(255, 255, 255, 0.08);
    transform: translateY(-2px);
    border-color: rgba(140, 90, 255, 0.25);
}
.hour-time { color: #8899AA; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.03em; }
.hour-icon { font-size: 1.9rem; margin: 0.5rem 0 0.3rem; line-height: 1; }
.hour-temp { color: #FFFFFF; font-size: 1.05rem; font-weight: 700; }

/* ── Headings ────────────────────────────────────────────────────────── */
h1, h2, h3, h4 {
    color: #FFFFFF !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em;
}

/* Section header */
.section-title {
    color: #FFFFFF;
    font-size: 1.05rem;
    font-weight: 700;
    margin-bottom: 0.8rem;
    letter-spacing: -0.01em;
}

/* ── Tabs ────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.4rem;
    background: transparent;
    border-bottom: none;
}
.stTabs [data-baseweb="tab"] {
    background: rgba(40, 50, 80, 0.4);
    border-radius: 12px;
    padding: 0.55rem 1.1rem;
    color: #8899AA;
    font-weight: 600;
    border: 1px solid transparent;
    transition: all 0.2s ease;
}
.stTabs [data-baseweb="tab"]:hover { background: rgba(60, 70, 110, 0.5); color: #FFFFFF; }
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(140, 90, 255, 0.25), rgba(98, 87, 255, 0.15)) !important;
    color: #FFFFFF !important;
    border-color: rgba(140, 90, 255, 0.3) !important;
}

/* ── Mini value boxes inside cards ───────────────────────────────────── */
.kpi-row { display: flex; align-items: baseline; gap: 0.3rem; }
.kpi-num { color: #FFFFFF; font-size: 2rem; font-weight: 700; letter-spacing: -0.03em; }
.kpi-unit { color: #8899AA; font-size: 0.95rem; font-weight: 500; }
.kpi-label { color: #8899AA; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.kpi-status { display: flex; align-items: center; gap: 0.45rem; font-size: 0.8rem; font-weight: 600; margin-top: 0.3rem; }
.kpi-dot { display: inline-block; width: 13px; height: 13px; border-radius: 50%; flex-shrink: 0; }
.dot-green  { background: #00D68F; }
.dot-yellow { background: #FFAA00; }
.dot-red    { background: #FF4444; }

/* ── 5-day forecast strip ────────────────────────────────────────────── */
.fc-strip { display: flex; gap: 0; width: 100%; }
.fc-day {
    flex: 1; display: flex; flex-direction: column; align-items: center;
    padding: 0.9rem 0.5rem; gap: 0.35rem;
    border-right: 1px solid rgba(255,255,255,0.06);
}
.fc-day:last-child { border-right: none; }
.fc-day-name { font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
               letter-spacing: 0.06em; color: #8899AA; }
.fc-icon { font-size: 1.6rem; line-height: 1; margin: 0.15rem 0; }
.fc-high { font-size: 1.05rem; font-weight: 700; color: #FFFFFF; }
.fc-low  { font-size: 0.82rem; font-weight: 500; color: #8899AA; }
.fc-cond { font-size: 0.7rem; color: #8899AA; margin-top: 0.1rem; }

/* ── Page header ─────────────────────────────────────────────────────── */
.page-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 1.5rem;
}
.page-title { font-size: 1.6rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.03em; }
.page-subtitle { color: #8899AA; font-size: 0.9rem; margin-top: 0.2rem; font-weight: 500; }
.page-pill {
    background: rgba(140, 90, 255, 0.12);
    color: #C9B6FF;
    padding: 0.5rem 1rem;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 600;
    border: 1px solid rgba(140, 90, 255, 0.2);
}

/* ── Alert rows ──────────────────────────────────────────────────────── */
.alert-row {
    padding: 0.7rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.alert-row:last-child { border-bottom: none; }
.alert-icon { font-size: 1.4rem; }
.alert-label { font-weight: 700; color: #FFFFFF; }
.alert-value { color: #8899AA; font-size: 0.85rem; margin-left: 2rem; margin-top: 0.1rem; }

/* ── Sun card ────────────────────────────────────────────────────────── */
.sun-row { display: flex; align-items: center; justify-content: center; gap: 0.8rem; padding: 0.6rem 0; }
.sun-icon { font-size: 1.5rem; }
.sun-label { color: #8899AA; font-size: 0.78rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.sun-value { color: #FFFFFF; font-size: 1.4rem; font-weight: 700; }
.sun-suffix { color: #8899AA; font-size: 0.85rem; font-weight: 500; margin-left: 0.3rem; }

/* Bootstrap icon sizing */
.bi { line-height: 1; vertical-align: -0.1em; }
.hero-icon .bi { font-size: 6rem; filter: drop-shadow(0 8px 24px rgba(255,200,100,0.2)); }
.hour-icon .bi { font-size: 1.9rem; }
.sun-icon .bi { font-size: 1.4rem; }
.alert-icon .bi { font-size: 1.3rem; }
</style>
""", unsafe_allow_html=True)

# ── BigQuery ──────────────────────────────────────────────────────────────────

DATASET = os.environ.get("BQ_DATASET_NAME", "weather_station")

COND_MAP = {
    "clear":        ("bi-sun-fill",                    "sun"),
    "clouds":       ("bi-cloud-fill",                  "cloud-fill"),
    "rain":         ("bi-cloud-rain-fill",              "cloud-rain-fill"),
    "drizzle":      ("bi-cloud-drizzle-fill",           "cloud-drizzle-fill"),
    "thunderstorm": ("bi-cloud-lightning-rain-fill",    "cloud-lightning-rain-fill"),
    "snow":         ("bi-snow",                        "cloud-snow-fill"),
    "mist":         ("bi-cloud-fog2-fill",              "cloud-haze2-fill"),
    "fog":          ("bi-cloud-fog2-fill",              "cloud-haze2-fill"),
    "haze":         ("bi-cloud-fog2-fill",              "cloud-haze2-fill"),
}


def cond_icon(condition: str) -> str:
    c = (condition or "").lower()
    cls = next((v[0] for k, v in COND_MAP.items() if k in c), "bi-cloud-sun-fill")
    return f'<i class="bi {cls}"></i>'


@st.cache_resource
def bq_client():
    import json
    from google.oauth2 import service_account
    # Local dev: load creds from a service-account JSON in the repo.
    if _CREDS_PATH:
        with open(_CREDS_PATH) as f:
            info = json.load(f)
        creds = service_account.Credentials.from_service_account_info(info)
        return bigquery.Client(project=info.get("project_id"), credentials=creds)
    # Cloud Run: no JSON file — Application Default Credentials come from
    # the runtime service account automatically.
    return bigquery.Client()


@st.cache_data(ttl=60)
def load_sensor(hours: int) -> pd.DataFrame:
    project = bq_client().project
    sql = f"""
        SELECT timestamp, temperature, humidity, tvoc, eco2
        FROM `{project}.{DATASET}.sensor_data`
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        ORDER BY timestamp ASC
    """
    try:
        df = bq_client().query(sql).to_dataframe()
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df
    except Exception as e:
        st.error(f"sensor_data query failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_weather(hours: int) -> pd.DataFrame:
    project = bq_client().project
    sql = f"""
        SELECT timestamp, temperature, outdoor_humidity, wind_speed, weather_condition
        FROM `{project}.{DATASET}.weather_data`
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        ORDER BY timestamp ASC
    """
    try:
        df = bq_client().query(sql).to_dataframe()
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df
    except Exception as e:
        st.error(f"weather_data query failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_daily_stats(days: int) -> pd.DataFrame:
    project = bq_client().project
    sql = f"""
        SELECT
            DATE(timestamp) AS day,
            MIN(temperature) AS min_t, MAX(temperature) AS max_t, AVG(temperature) AS avg_t,
            MIN(humidity)    AS min_h, MAX(humidity)    AS max_h, AVG(humidity)    AS avg_h,
            AVG(tvoc) AS avg_tvoc, AVG(eco2) AS avg_eco2,
            COUNT(*) AS readings
        FROM `{project}.{DATASET}.sensor_data`
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
        GROUP BY day ORDER BY day DESC
    """
    try:
        df = bq_client().query(sql).to_dataframe()
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
        return df
    except Exception as e:
        st.error(f"daily stats query failed: {e}")
        return pd.DataFrame()


# ── Chart helpers ─────────────────────────────────────────────────────────────

GRID = "rgba(140, 150, 180, 0.10)"


def base_layout(height=320):
    return dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#8899AA", size=11),
        margin=dict(l=10, r=10, t=20, b=10),
        height=height,
        xaxis=dict(gridcolor=GRID, linecolor=GRID, showgrid=True, zeroline=False),
        yaxis=dict(gridcolor=GRID, linecolor=GRID, showgrid=True, zeroline=False),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h",
                    yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
    )


def sparkline(values, color="#8C5AFF", height=60):
    """Tiny inline chart — area fill, no axes, used inside highlight cards."""
    fig = go.Figure()
    if values is not None and len(values) > 0:
        fig.add_trace(go.Scatter(
            y=list(values), mode="lines",
            line=dict(color=color, width=2, shape="spline"),
            fill="tozeroy",
            fillcolor=f"rgba{tuple(list(int(color.lstrip('#')[i:i+2], 16) for i in (0,2,4)) + [0.15])}",
            hoverinfo="skip", showlegend=False,
        ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=4, b=0), height=height,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


# ── Location presets & session state ─────────────────────────────────────────

CITY_PRESETS = [
    {"city": "Lausanne",  "lat": "46.5197", "lon": "6.6323",   "country": "CH"},
    {"city": "Geneva",    "lat": "46.2044", "lon": "6.1432",   "country": "CH"},
    {"city": "Zurich",    "lat": "47.3769", "lon": "8.5417",   "country": "CH"},
    {"city": "Paris",     "lat": "48.8566", "lon": "2.3522",   "country": "FR"},
    {"city": "London",    "lat": "51.5074", "lon": "-0.1278",  "country": "GB"},
    {"city": "Madrid",    "lat": "40.4168", "lon": "-3.7038",  "country": "ES"},
    {"city": "Barcelona", "lat": "41.3851", "lon": "2.1734",   "country": "ES"},
    {"city": "New York",  "lat": "40.7128", "lon": "-74.0060", "country": "US"},
    {"city": "Tokyo",     "lat": "35.6762", "lon": "139.6503", "country": "JP"},
    {"city": "Dubai",     "lat": "25.2048", "lon": "55.2708",  "country": "AE"},
]

_pages = ["Overview", "Trends", "Air Quality", "Outdoor", "Statistics", "Location"]
if "page" not in st.session_state:
    _page_qp = st.query_params.get("page", "Overview")
    st.session_state["page"] = _page_qp if _page_qp in _pages else "Overview"

if "loc" not in st.session_state:
    _city_qp = st.query_params.get("city", "")
    _lat_qp  = st.query_params.get("lat",  "")
    _lon_qp  = st.query_params.get("lon",  "")
    _qp_preset = next((p for p in CITY_PRESETS if p["city"] == _city_qp), None)
    if _qp_preset:
        st.session_state["loc"] = _qp_preset
    elif _city_qp and _lat_qp and _lon_qp:
        st.session_state["loc"] = {"city": _city_qp, "lat": _lat_qp, "lon": _lon_qp, "country": ""}
    else:
        st.session_state["loc"] = CITY_PRESETS[0]


@st.cache_data(ttl=300)
def fetch_live_weather(lat: str, lon: str) -> dict:
    """Direct OWM call for the dashboard's selected location."""
    try:
        from weather_client import get_current_weather
        return get_current_weather(lat, lon)
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=300)
def fetch_weather_by_city(city: str) -> dict:
    try:
        from weather_client import get_weather_by_city
        return get_weather_by_city(city)
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=1800)
def fetch_5day_forecast(lat: str, lon: str) -> list:
    try:
        from weather_client import get_5day_forecast
        result = get_5day_forecast(lat, lon)
        return result.get("forecast", [])
    except Exception as e:
        return []


# ── Sidebar ───────────────────────────────────────────────────────────────────

_logo_hour = datetime.now().hour
_logo_is_night = _logo_hour < 6 or _logo_hour >= 20
_logo_icon = "bi-cloud-moon-fill" if _logo_is_night else "bi-cloud-sun-fill"

# Adaptive nav palette — mirrors time_of_day_css logic
if _logo_is_night:
    _nav_sel_bg   = "linear-gradient(135deg, rgba(140,90,255,0.25), rgba(98,87,255,0.15))"
    _nav_sel_shadow = "0 0 0 1px rgba(140,90,255,0.30), inset 0 1px 0 rgba(255,255,255,0.05)"
    _nav_icon_sel = "#C9B6FF"
    # Dark navy with a faint purple tint — matches the night sky/star theme
    _menu_box_bg     = "linear-gradient(165deg, rgba(22, 18, 48, 0.92), rgba(14, 16, 36, 0.92))"
    _menu_box_border = "1px solid rgba(140, 90, 255, 0.20)"
elif _logo_hour < 12:  # morning
    _nav_sel_bg   = "linear-gradient(135deg, rgba(246,201,14,0.28), rgba(92,184,228,0.18))"
    _nav_sel_shadow = "0 0 0 1px rgba(246,201,14,0.40), inset 0 1px 0 rgba(255,255,255,0.08)"
    _nav_icon_sel = "#F6C90E"
    # Deep ocean blue with a hint of sky — picks up the morning palette
    _menu_box_bg     = "linear-gradient(165deg, rgba(14, 34, 70, 0.90), rgba(18, 50, 96, 0.90))"
    _menu_box_border = "1px solid rgba(92, 184, 228, 0.28)"
else:  # afternoon
    _nav_sel_bg   = "linear-gradient(135deg, rgba(255,124,42,0.28), rgba(69,179,224,0.18))"
    _nav_sel_shadow = "0 0 0 1px rgba(255,124,42,0.40), inset 0 1px 0 rgba(255,255,255,0.08)"
    _nav_icon_sel = "#FF7C2A"
    # Warm dark espresso with an amber edge — matches the golden-hour palette
    _menu_box_bg     = "linear-gradient(165deg, rgba(44, 26, 14, 0.92), rgba(32, 18, 10, 0.92))"
    _menu_box_border = "1px solid rgba(255, 124, 42, 0.28)"

with st.sidebar:
    st.markdown(f"""
    <div style="text-align:center; padding: 0.5rem 0 1.5rem;">
        <div style="
            display:inline-flex; align-items:center; justify-content:center;
            width: 56px; height: 56px;
            background: linear-gradient(135deg, #8C5AFF 0%, #4A8FFF 100%);
            border-radius: 16px;
            box-shadow: 0 8px 24px rgba(140, 90, 255, 0.3);
            font-size: 1.8rem; color:#fff;
        "><i class="bi {_logo_icon}"></i></div>
        <div style="font-size: 1.2rem; font-weight: 800; color:#FFFFFF; margin-top:0.6rem; letter-spacing:-0.02em;">SkySense</div>
        <div style="font-size: 0.72rem; color:#8899AA; font-weight: 500; letter-spacing: 0.05em; text-transform: uppercase;">M5Stack · {st.session_state["loc"].get("city", "Lausanne")}</div>
    </div>
    """, unsafe_allow_html=True)

    _default_idx = _pages.index(st.session_state.get("page", "Overview"))

    selected = option_menu(
        menu_title=None,
        options=_pages,
        icons=["house-door-fill", "graph-up-arrow", "wind", "cloud-sun-fill", "bar-chart-line-fill", "geo-alt-fill"],
        default_index=_default_idx,
        styles={
            "container": {
                "padding": "0.55rem 0.5rem",
                "background-color": _menu_box_bg,
                "background": _menu_box_bg,
                "border-radius": "20px",
                "border": _menu_box_border,
                "backdrop-filter": "blur(18px) saturate(180%)",
                "-webkit-backdrop-filter": "blur(18px) saturate(180%)",
                "box-shadow": "0 4px 20px rgba(0,0,0,0.18), inset 0 1px 0 rgba(255,255,255,0.06)",
            },
            "icon": {"color": "#8899AA", "font-size": "18px"},
            "nav-link": {
                "color": "#8899AA",
                "font-size": "0.9rem",
                "font-weight": "500",
                "padding": "0.7rem 1rem",
                "border-radius": "16px",
                "margin": "0.15rem 0",
                "text-align": "left",
                "transition": "transform 0.18s ease, background 0.18s ease, color 0.18s ease",
            },
            "nav-link-selected": {
                "background": _nav_sel_bg,
                "box-shadow": _nav_sel_shadow,
                "color": "#FFFFFF",
                "font-weight": "600",
                "border-radius": "16px",
                "icon-color": _nav_icon_sel,
            },
        },
    )

    if selected != st.session_state.get("page"):
        st.session_state["page"] = selected

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)
    st.markdown("<div style='color:#8899AA; font-size:0.72rem; font-weight:600; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.4rem;'>Time Range</div>", unsafe_allow_html=True)

    hours = st.select_slider(
        "Time range",
        options=[6, 12, 24, 48, 72, 168],
        value=24,
        format_func=lambda h: f"{h}h" if h < 48 else f"{h//24}d",
        label_visibility="collapsed",
    )

    st.markdown("<div style='height: 0.8rem'></div>", unsafe_allow_html=True)
    if st.button("↺  Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown(f"""
    <div style='margin-top: 2rem; padding-top: 1rem; border-top: 1px solid rgba(255,255,255,0.05);'>
        <div style='color:#556677; font-size:0.7rem; font-weight:600; text-transform:uppercase; letter-spacing:0.05em;'>Location</div>
        <div style='color:#FFFFFF; font-size:0.85rem; font-weight:600; margin-top:0.2rem;'>
            <i class="bi bi-geo-alt-fill" style="color:#8C5AFF; margin-right:0.3rem;"></i>
            {st.session_state["loc"]["city"]}, {st.session_state["loc"]["country"]}
        </div>
        <div style='color:#556677; font-size:0.7rem; font-weight:600; text-transform:uppercase; letter-spacing:0.05em; margin-top:0.8rem;'>Last Updated</div>
        <div style='color:#FFFFFF; font-size:0.85rem; font-weight:600; margin-top:0.2rem;'>{datetime.now(timezone.utc).strftime('%d %b · %H:%M UTC')}</div>
    </div>
    """, unsafe_allow_html=True)

# Inject hover CSS into the option_menu iframe (same-origin, so cross-frame JS is allowed)
import streamlit.components.v1 as _components
_components.html("""<script>
(function () {
    var css = [
        '.nav-link { transition: transform 0.18s ease, background 0.18s ease, color 0.18s ease !important; }',
        '.nav-link:not(.nav-link-selected):hover {',
        '  transform: translateX(5px) !important;',
        '  background: rgba(255,255,255,0.07) !important;',
        '  color: rgba(255,255,255,0.88) !important;',
        '}'
    ].join('\\n');

    function inject() {
        try {
            var sidebar = window.parent.document.querySelector('section[data-testid="stSidebar"]');
            if (!sidebar) return;
            sidebar.querySelectorAll('iframe').forEach(function (f) {
                try {
                    var doc = f.contentDocument;
                    if (!doc || doc.getElementById('__nav_hover')) return;
                    if (!doc.querySelector('.nav-link')) return;
                    var s = doc.createElement('style');
                    s.id = '__nav_hover';
                    s.textContent = css;
                    doc.head.appendChild(s);
                } catch (e) {}
            });
        } catch (e) {}
    }

    inject();
    setInterval(inject, 800);
})();
</script>""", height=0)

# ── Load data ─────────────────────────────────────────────────────────────────

sensor_df = load_sensor(hours)
weather_df = load_weather(hours)

latest = sensor_df.iloc[-1].to_dict() if not sensor_df.empty else {}
latest_wx = weather_df.iloc[-1].to_dict() if not weather_df.empty else {}

t = float(latest["temperature"]) if latest.get("temperature") is not None else None
h = float(latest["humidity"]) if latest.get("humidity") is not None else None
tv = float(latest["tvoc"]) if latest.get("tvoc") is not None else None
co = float(latest["eco2"]) if latest.get("eco2") is not None else None

# Live outdoor weather for the selected location (OWM direct, not BigQuery)
_loc = st.session_state["loc"]
_live_wx = fetch_live_weather(_loc["lat"], _loc["lon"])
if "error" not in _live_wx:
    _lm = _live_wx.get("main", {})
    ot = _lm.get("temp")
    oh = _lm.get("humidity")
    ow = _live_wx.get("wind", {}).get("speed")
    oc = _live_wx.get("weather", [{}])[0].get("main", "").lower()
else:
    # Fallback to BigQuery last row if OWM call fails
    ot = float(latest_wx["temperature"]) if latest_wx.get("temperature") is not None else None
    oh = float(latest_wx["outdoor_humidity"]) if latest_wx.get("outdoor_humidity") is not None else None
    ow = float(latest_wx["wind_speed"]) if latest_wx.get("wind_speed") is not None else None
    oc = str(latest_wx.get("weather_condition") or "").lower()
wx_icon = cond_icon(oc)


# ── Weather-aware background ──────────────────────────────────────────────────

def _astral_sun(lat: str, lon: str):
    from astral import LocationInfo
    from astral.sun import sun as astral_sun
    try:
        from timezonefinder import TimezoneFinder
        tz = TimezoneFinder().timezone_at(lat=float(lat), lng=float(lon)) or "UTC"
    except Exception:
        tz = "UTC"
    loc = LocationInfo(latitude=float(lat), longitude=float(lon), timezone=tz)
    return astral_sun(loc.observer, date=datetime.now().date(), tzinfo=loc.timezone)


def _is_night_loc(lat: str, lon: str) -> bool:
    try:
        s = _astral_sun(lat, lon)
        now = datetime.now(s["sunrise"].tzinfo)
        return now < s["sunrise"] or now > s["sunset"]
    except Exception:
        h = datetime.now().hour
        return h < 6 or h >= 22


def weather_background_css(condition: str, is_night: bool) -> str:
    c = (condition or "").lower()
    # (background-image, decorative-overlay-html)
    if is_night:
        if "thunderstorm" in c:
            grad = ("radial-gradient(ellipse 900px 500px at 30% 0%, rgba(140, 90, 255, 0.20), transparent 60%),"
                    " radial-gradient(ellipse 600px 400px at 80% 30%, rgba(70, 100, 200, 0.10), transparent 60%),"
                    " linear-gradient(180deg, #0F0820 0%, #050308 100%)")
        elif "snow" in c:
            grad = ("radial-gradient(ellipse 800px 500px at 50% 0%, rgba(180, 200, 255, 0.10), transparent 60%),"
                    " linear-gradient(180deg, #0E1830 0%, #060B18 100%)")
        elif "rain" in c or "drizzle" in c:
            grad = ("radial-gradient(ellipse 700px 400px at 70% 0%, rgba(60, 120, 200, 0.12), transparent 60%),"
                    " linear-gradient(180deg, #051528 0%, #06101A 100%)")
        elif any(k in c for k in ["mist", "fog", "haze"]):
            grad = "linear-gradient(180deg, #11161E 0%, #060A10 100%)"
        elif "clear" in c:
            grad = ("radial-gradient(ellipse 700px 500px at 80% 5%, rgba(180, 150, 255, 0.18), transparent 55%),"
                    " radial-gradient(circle 250px at 80% 8%, rgba(220, 220, 255, 0.10), transparent 70%),"
                    " linear-gradient(180deg, #06080F 0%, #0A0E1A 100%)")
        else:  # clouds / default night
            grad = ("radial-gradient(ellipse 800px 400px at 100% 0%, rgba(90, 100, 160, 0.10), transparent 60%),"
                    " linear-gradient(180deg, #0A0E1A 0%, #06080F 100%)")
    else:
        if "thunderstorm" in c:
            grad = ("radial-gradient(ellipse 900px 500px at 30% 0%, rgba(140, 90, 255, 0.18), transparent 60%),"
                    " linear-gradient(180deg, #1A0E2E 0%, #0A0815 100%)")
        elif "snow" in c:
            grad = ("radial-gradient(ellipse 800px 500px at 50% 0%, rgba(220, 230, 255, 0.12), transparent 60%),"
                    " linear-gradient(180deg, #1A2540 0%, #0F1830 100%)")
        elif "rain" in c:
            grad = ("radial-gradient(ellipse 700px 400px at 70% 0%, rgba(60, 130, 220, 0.15), transparent 60%),"
                    " linear-gradient(180deg, #0E2440 0%, #061525 100%)")
        elif "drizzle" in c:
            grad = ("radial-gradient(ellipse 700px 400px at 70% 0%, rgba(80, 150, 220, 0.12), transparent 60%),"
                    " linear-gradient(180deg, #142C45 0%, #081628 100%)")
        elif any(k in c for k in ["mist", "fog", "haze"]):
            grad = ("radial-gradient(ellipse 1000px 500px at 50% 0%, rgba(180, 195, 220, 0.08), transparent 60%),"
                    " linear-gradient(180deg, #1F2B3D 0%, #131C28 100%)")
        elif "clear" in c:
            grad = ("radial-gradient(ellipse 1000px 600px at 90% 0%, rgba(255, 180, 80, 0.20), transparent 50%),"
                    " radial-gradient(circle 220px at 90% 8%, rgba(255, 220, 130, 0.18), transparent 70%),"
                    " linear-gradient(180deg, #1A2545 0%, #0E1525 100%)")
        else:  # clouds / default day
            grad = ("radial-gradient(ellipse 800px 500px at 100% 0%, rgba(140, 160, 200, 0.10), transparent 60%),"
                    " linear-gradient(180deg, #1B2845 0%, #0E1525 100%)")

    return f"""
<style>
.stApp {{
    background: {grad} !important;
    transition: background 0.8s ease;
}}
</style>
"""


def _get_time_period(lat: str, lon: str) -> str:
    """Returns 'morning', 'afternoon', or 'night' based on the selected location's local time."""
    try:
        s = _astral_sun(lat, lon)
        now = datetime.now(s["sunrise"].tzinfo)
        if now < s["sunrise"] or now > s["sunset"]:
            return "night"
        noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
        return "morning" if now < noon else "afternoon"
    except Exception:
        h = datetime.now().hour
        if h < 6 or h >= 20:
            return "night"
        return "morning" if h < 12 else "afternoon"


def time_of_day_css(period: str) -> str:
    """Injects a CSS palette overlay based on time of day."""
    if period == "night":
        return ""

    if period == "morning":
        # sky blues, whites, yellows
        pri, pri_r = "#F6C90E", "246, 201, 14"
        pri_dark   = "#C9A008"
        sec, sec_r = "#5CB8E4", "92, 184, 228"
        app_bg = (
            "radial-gradient(ellipse 900px 500px at 85% 0%, rgba(255, 235, 80, 0.55), transparent 52%),"
            " radial-gradient(ellipse 600px 500px at 8% 95%, rgba(92, 184, 228, 0.35), transparent 58%),"
            " linear-gradient(180deg, #5BB8E8 0%, #A8D8F0 35%, #DCEFFD 65%, #FEFCE8 100%)"
        )
        txt_main  = "#0A2540"
        txt_sub   = "#2A5070"
        hero_bg   = "radial-gradient(ellipse 400px 200px at 100% 0%, rgba(255,220,60,0.20), transparent), rgba(10,40,100,0.35)"
    else:
        # light blue and orange (afternoon / golden hour)
        pri, pri_r = "#FF7C2A", "255, 124, 42"
        pri_dark   = "#C85A0A"
        sec, sec_r = "#45B3E0", "69, 179, 224"
        app_bg = (
            "radial-gradient(ellipse 900px 500px at 82% 0%, rgba(255, 140, 40, 0.55), transparent 52%),"
            " radial-gradient(ellipse 600px 500px at 6% 95%, rgba(69, 179, 224, 0.35), transparent 58%),"
            " linear-gradient(180deg, #4A9FCC 0%, #85C8E8 30%, #FFD59A 65%, #FFBD78 100%)"
        )
        txt_main  = "#1A0A00"
        txt_sub   = "#5C3A10"
        hero_bg   = "radial-gradient(ellipse 400px 200px at 100% 0%, rgba(255,140,40,0.20), transparent), rgba(30,10,0,0.35)"

    return f"""<style>
/* ── {period.capitalize()} palette ─────────────────────────────────────── */
.stApp {{
    background: {app_bg} !important;
    transition: background 1.2s ease;
}}
/* Text that sits on the app background (outside cards) */
.page-title {{ color: {txt_main} !important; }}
.page-subtitle {{ color: {txt_sub} !important; }}
.section-title {{ color: {txt_main} !important; }}
.page-pill {{
    background: rgba({pri_r}, 0.15) !important;
    color: {txt_main} !important;
    border-color: rgba({pri_r}, 0.35) !important;
}}
/* Cards: darker glass tint so content stays legible on bright background */
[data-testid="stVerticalBlockBorderWrapper"] {{
    background: rgba(0, 0, 0, 0.14) !important;
    border-color: rgba(255,255,255,0.45) !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.12), inset 0 1px 0 rgba(255,255,255,0.55) !important;
}}
[data-testid="stMetric"] {{
    background: rgba(0, 0, 0, 0.12) !important;
    border-color: rgba(255,255,255,0.40) !important;
}}
.hero-card {{
    background: {hero_bg} !important;
    border-color: rgba(255,255,255,0.35) !important;
}}
.hour-card {{
    background: rgba(0, 0, 0, 0.12) !important;
    border-color: rgba(255,255,255,0.35) !important;
}}
/* Nav selected pill */
.nav-link-selected {{
    background: linear-gradient(135deg, rgba({pri_r}, 0.28) 0%, rgba({sec_r}, 0.16) 100%) !important;
    box-shadow: 0 0 0 1px rgba({pri_r}, 0.40), inset 0 1px 0 rgba(255,255,255,0.08) !important;
}}
/* Tabs selected */
.stTabs [aria-selected="true"] {{
    background: linear-gradient(135deg, rgba({pri_r}, 0.28), rgba({sec_r}, 0.16)) !important;
    border-color: rgba({pri_r}, 0.38) !important;
    color: #FFFFFF !important;
}}
/* Slider gradient */
section[data-testid="stSidebar"] [data-testid="stSlider"] > div > div > div > div {{
    background: linear-gradient(90deg, {pri} 0%, {sec} 100%) !important;
}}
section[data-testid="stSidebar"] [data-testid="stSlider"] [role="slider"]:focus,
section[data-testid="stSidebar"] [data-testid="stSlider"] [role="slider"]:active {{
    box-shadow: 0 0 0 3px rgba({pri_r}, 0.45) !important;
}}
/* Sidebar refresh button */
section[data-testid="stSidebar"] .stButton > button {{
    background: rgba({pri_r}, 0.22) !important;
    color: {pri_dark} !important;
    border-color: rgba({pri_r}, 0.50) !important;
}}
section[data-testid="stSidebar"] .stButton > button:hover {{
    background: rgba({pri_r}, 0.34) !important;
    border-color: rgba({pri_r}, 0.70) !important;
}}
/* Sidebar expand button */
button[data-testid="stExpandSidebarButton"],
[data-testid="stExpandSidebarButton"] {{
    border-color: rgba({pri_r}, 0.30) !important;
}}
button[data-testid="stExpandSidebarButton"] svg,
button[data-testid="stExpandSidebarButton"] path,
[data-testid="stExpandSidebarButton"] svg,
[data-testid="stExpandSidebarButton"] path {{
    fill: {pri} !important; color: {pri} !important; stroke: {pri} !important;
}}
/* Hero card — daytime palette */
.hero-card::before {{
    background: radial-gradient(circle, rgba({pri_r}, 0.22) 0%, transparent 70%);
}}
.hero-loc {{
    background: rgba({pri_r}, 0.22) !important;
    color: {txt_main} !important;
    border-color: rgba({pri_r}, 0.40) !important;
}}
.hero-temp {{
    background: linear-gradient(180deg, {txt_main} 0%, rgba({sec_r}, 1.0) 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
}}
.hero-day {{ color: {txt_main} !important; }}
.hero-date {{ color: {txt_sub} !important; }}
.hero-range {{ color: {txt_sub} !important; }}
.hero-cond {{ color: {txt_main} !important; }}
.hero-feels {{ color: {txt_sub} !important; }}
.hero-icon {{ filter: drop-shadow(0 8px 24px rgba({pri_r}, 0.40)) !important; }}
</style>"""


def sidebar_animation_css(condition: str, is_night: bool, time_period: str = "night") -> str:
    """Animates both the sidebar background and the full app background.

    Sidebar: multi-layer background with animated position.
    App background: ::before pseudo-element (position:fixed, pointer-events:none)
    so it sits above the gradient but below all page content.
    """
    c = (condition or "").lower()

    # Adaptive solid base: tinted to match the time-of-day palette
    if time_period == "morning":
        _solid = "rgba(12, 35, 85, 0.32)"
    elif time_period == "afternoon":
        _solid = "rgba(38, 20, 8, 0.32)"
    else:
        _solid = "rgba(8, 12, 24, 0.38)"

    # Ensure main content block renders above the app ::before layer,
    # and preserve sidebar border-radius set in the base CSS.
    _layout = """.block-container { position: relative !important; z-index: 1 !important; }
section[data-testid="stSidebar"] { border-radius: 20px !important; }"""

    # ── Rain / Drizzle / Thunderstorm ─────────────────────────────────────────
    if "thunderstorm" in c or "rain" in c or "drizzle" in c:
        if "thunderstorm" in c:
            sb_a, bg_a, speed = "0.22", "0.07", "0.45s"
        elif "drizzle" in c:
            sb_a, bg_a, speed = "0.12", "0.04", "0.9s"
        else:
            sb_a, bg_a, speed = "0.18", "0.06", "0.6s"
        return f"""<style>
@keyframes sk-rain {{
    from {{ background-position: 0 0,         center; }}
    to   {{ background-position: -20px 700px, center; }}
}}
{_layout}
section[data-testid="stSidebar"] {{
    background:
        repeating-linear-gradient(172deg,
            transparent 0px, transparent 3px,
            rgba(130, 185, 255, {sb_a}) 3px, rgba(130, 185, 255, {sb_a}) 4px,
            transparent 4px, transparent 14px),
        {_solid} !important;
    background-size: 8px 80px, 100% 100% !important;
    animation: sk-rain {speed} linear infinite !important;
}}
.stApp::before {{
    content: ""; position: fixed; inset: 0; pointer-events: none;
    background: repeating-linear-gradient(172deg,
        transparent 0px, transparent 3px,
        rgba(130, 185, 255, {bg_a}) 3px, rgba(130, 185, 255, {bg_a}) 4px,
        transparent 4px, transparent 14px);
    background-size: 8px 80px;
    animation: sk-rain {speed} linear infinite;
}}
</style>"""

    # ── Snow ──────────────────────────────────────────────────────────────────
    if "snow" in c:
        return f"""<style>
@keyframes sk-snow {{
    from {{ background-position: 0 0,        30px -20px, 15px 10px, center; }}
    to   {{ background-position: 15px 700px, 45px 680px, 25px 720px, center; }}
}}
{_layout}
section[data-testid="stSidebar"] {{
    background:
        radial-gradient(circle 2px   at 50% 50%, rgba(220,235,255,0.72) 100%, transparent),
        radial-gradient(circle 1.5px at 50% 50%, rgba(200,220,255,0.55) 100%, transparent),
        radial-gradient(circle 1px   at 50% 50%, rgba(210,230,255,0.48) 100%, transparent),
        {_solid} !important;
    background-size: 38px 76px, 55px 110px, 28px 55px, 100% 100% !important;
    animation: sk-snow 5s linear infinite !important;
}}
.stApp::before {{
    content: ""; position: fixed; inset: 0; pointer-events: none;
    background:
        radial-gradient(circle 2px   at 50% 50%, rgba(220,235,255,0.30) 100%, transparent),
        radial-gradient(circle 1.5px at 50% 50%, rgba(200,220,255,0.22) 100%, transparent),
        radial-gradient(circle 1px   at 50% 50%, rgba(210,230,255,0.18) 100%, transparent);
    background-size: 38px 76px, 55px 110px, 28px 55px;
    animation: sk-snow 5s linear infinite;
}}
</style>"""

    # ── Clear night — twinkling stars ─────────────────────────────────────────
    if "clear" in c and is_night:
        return f"""<style>
@keyframes sk-stars {{
    0%, 100% {{ opacity: 0.75; }}
    50%       {{ opacity: 1.00; }}
}}
{_layout}
section[data-testid="stSidebar"] {{
    background:
        radial-gradient(circle 1px at 18% 12%, rgba(255,255,255,0.75) 100%, transparent),
        radial-gradient(circle 1px at 52%  7%, rgba(255,255,255,0.60) 100%, transparent),
        radial-gradient(circle 2px at 78% 21%, rgba(255,255,255,0.70) 100%, transparent),
        radial-gradient(circle 1px at 33% 33%, rgba(255,255,255,0.50) 100%, transparent),
        radial-gradient(circle 1px at 65% 44%, rgba(255,255,255,0.55) 100%, transparent),
        radial-gradient(circle 1px at 10% 58%, rgba(255,255,255,0.40) 100%, transparent),
        radial-gradient(circle 1px at 88% 62%, rgba(255,255,255,0.45) 100%, transparent),
        radial-gradient(circle 2px at 44% 18%, rgba(255,255,255,0.65) 100%, transparent),
        radial-gradient(circle 1px at 72% 75%, rgba(255,255,255,0.38) 100%, transparent),
        {_solid} !important;
    background-size: 100% 100% !important;
    animation: sk-stars 3.5s ease-in-out infinite !important;
}}
.stApp::before {{
    content: ""; position: fixed; inset: 0; pointer-events: none;
    background:
        radial-gradient(circle 1px at 12% 8%,  rgba(255,255,255,0.55) 100%, transparent),
        radial-gradient(circle 1px at 35% 15%, rgba(255,255,255,0.45) 100%, transparent),
        radial-gradient(circle 2px at 68% 5%,  rgba(255,255,255,0.50) 100%, transparent),
        radial-gradient(circle 1px at 85% 22%, rgba(255,255,255,0.40) 100%, transparent),
        radial-gradient(circle 1px at 20% 40%, rgba(255,255,255,0.35) 100%, transparent),
        radial-gradient(circle 1px at 50% 30%, rgba(255,255,255,0.42) 100%, transparent),
        radial-gradient(circle 2px at 75% 48%, rgba(255,255,255,0.38) 100%, transparent),
        radial-gradient(circle 1px at 90% 65%, rgba(255,255,255,0.32) 100%, transparent),
        radial-gradient(circle 1px at 42% 70%, rgba(255,255,255,0.30) 100%, transparent),
        radial-gradient(circle 1px at 8%  80%, rgba(255,255,255,0.28) 100%, transparent),
        radial-gradient(circle 2px at 60% 85%, rgba(255,255,255,0.35) 100%, transparent),
        radial-gradient(circle 1px at 28% 92%, rgba(255,255,255,0.25) 100%, transparent);
    background-size: 100% 100%;
    animation: sk-stars 3.5s ease-in-out infinite;
}}
</style>"""

    # ── Clear day — sun shimmer sweep ─────────────────────────────────────────
    if "clear" in c and not is_night:
        return f"""<style>
@keyframes sk-shine {{
    from {{ background-position: -100% center, center; }}
    to   {{ background-position:  200% center, center; }}
}}
{_layout}
section[data-testid="stSidebar"] {{
    background:
        linear-gradient(105deg, transparent 10%, rgba(255,230,100,0.42) 50%, transparent 90%),
        {_solid} !important;
    background-size: 60% 100%, 100% 100% !important;
    animation: sk-shine 5.5s ease-in-out infinite !important;
}}
.stApp::before {{
    content: ""; position: fixed; inset: 0; pointer-events: none;
    background: linear-gradient(105deg, transparent 10%, rgba(255,230,100,0.15) 50%, transparent 90%);
    background-size: 60% 100%;
    animation: sk-shine 5.5s ease-in-out infinite;
}}
</style>"""

    # ── Mist / Fog / Haze — drifting bands ───────────────────────────────────
    if any(k in c for k in ["mist", "fog", "haze"]):
        return f"""<style>
@keyframes sk-fog {{
    0%,100% {{ background-position: 0%  center, 100% center, center; }}
    50%      {{ background-position: 20% center, 80%  center, center; }}
}}
{_layout}
section[data-testid="stSidebar"] {{
    background:
        radial-gradient(ellipse 80% 25% at 50% 30%, rgba(200,215,230,0.32) 0%, transparent 70%),
        radial-gradient(ellipse 70% 22% at 50% 65%, rgba(180,200,220,0.26) 0%, transparent 70%),
        {_solid} !important;
    background-size: 150% 100%, 150% 100%, 100% 100% !important;
    animation: sk-fog 9s ease-in-out infinite !important;
}}
.stApp::before {{
    content: ""; position: fixed; inset: 0; pointer-events: none;
    background:
        radial-gradient(ellipse 80% 35% at 50% 25%, rgba(200,215,230,0.12) 0%, transparent 70%),
        radial-gradient(ellipse 70% 30% at 50% 70%, rgba(180,200,220,0.09) 0%, transparent 70%);
    background-size: 150% 100%, 150% 100%;
    animation: sk-fog 9s ease-in-out infinite;
}}
</style>"""

    # ── Clouds — slow drifting blobs ──────────────────────────────────────────
    if "clouds" in c:
        return f"""<style>
@keyframes sk-cloud {{
    0%,100% {{ background-position: 0%  center, 100% center, center; }}
    50%      {{ background-position: 20% center, 80%  center, center; }}
}}
{_layout}
section[data-testid="stSidebar"] {{
    background:
        radial-gradient(ellipse 80% 22% at 50% 25%, rgba(180,200,230,0.30) 0%, transparent 70%),
        radial-gradient(ellipse 70% 18% at 50% 65%, rgba(160,185,220,0.24) 0%, transparent 70%),
        {_solid} !important;
    background-size: 150% 100%, 150% 100%, 100% 100% !important;
    animation: sk-cloud 16s ease-in-out infinite !important;
}}
.stApp::before {{
    content: ""; position: fixed; inset: 0; pointer-events: none;
    background:
        radial-gradient(ellipse 80% 30% at 50% 20%, rgba(180,200,230,0.11) 0%, transparent 70%),
        radial-gradient(ellipse 70% 25% at 50% 68%, rgba(160,185,220,0.09) 0%, transparent 70%);
    background-size: 150% 100%, 150% 100%;
    animation: sk-cloud 16s ease-in-out infinite;
}}
</style>"""

    # ── Fallbacks — always show something ────────────────────────────────────
    if is_night:
        return f"""<style>
@keyframes sk-stars {{
    0%, 100% {{ opacity: 0.65; }}
    50%       {{ opacity: 1.00; }}
}}
{_layout}
section[data-testid="stSidebar"] {{
    background:
        radial-gradient(circle 1px at 22% 10%, rgba(255,255,255,0.55) 100%, transparent),
        radial-gradient(circle 1px at 60%  6%, rgba(255,255,255,0.45) 100%, transparent),
        radial-gradient(circle 1px at 80% 25%, rgba(255,255,255,0.50) 100%, transparent),
        radial-gradient(circle 1px at 38% 38%, rgba(255,255,255,0.40) 100%, transparent),
        radial-gradient(circle 2px at 55% 55%, rgba(255,255,255,0.48) 100%, transparent),
        radial-gradient(circle 1px at 14% 65%, rgba(255,255,255,0.35) 100%, transparent),
        {_solid} !important;
    background-size: 100% 100% !important;
    animation: sk-stars 4s ease-in-out infinite !important;
}}
.stApp::before {{
    content: ""; position: fixed; inset: 0; pointer-events: none;
    background:
        radial-gradient(circle 1px at 10% 5%,  rgba(255,255,255,0.40) 100%, transparent),
        radial-gradient(circle 1px at 30% 12%, rgba(255,255,255,0.35) 100%, transparent),
        radial-gradient(circle 2px at 55%  3%, rgba(255,255,255,0.38) 100%, transparent),
        radial-gradient(circle 1px at 78% 18%, rgba(255,255,255,0.30) 100%, transparent),
        radial-gradient(circle 1px at 18% 35%, rgba(255,255,255,0.28) 100%, transparent),
        radial-gradient(circle 1px at 45% 48%, rgba(255,255,255,0.32) 100%, transparent),
        radial-gradient(circle 2px at 82% 42%, rgba(255,255,255,0.28) 100%, transparent),
        radial-gradient(circle 1px at 65% 72%, rgba(255,255,255,0.25) 100%, transparent),
        radial-gradient(circle 1px at 25% 80%, rgba(255,255,255,0.22) 100%, transparent),
        radial-gradient(circle 1px at 90% 88%, rgba(255,255,255,0.20) 100%, transparent);
    background-size: 100% 100%;
    animation: sk-stars 4s ease-in-out infinite;
}}
</style>"""

    # Daytime fallback — ambient glow pulse
    return f"""<style>
@keyframes sk-ambient {{
    0%,100% {{ opacity: 0.55; }}
    50%      {{ opacity: 1.00; }}
}}
{_layout}
section[data-testid="stSidebar"] {{
    background:
        radial-gradient(ellipse 90% 40% at 50% 0%,  rgba(140,160,220,0.38) 0%, transparent 70%),
        radial-gradient(ellipse 70% 30% at 50% 100%, rgba(100,130,200,0.28) 0%, transparent 70%),
        {_solid} !important;
    background-size: 100% 100% !important;
    animation: sk-ambient 6s ease-in-out infinite !important;
}}
.stApp::before {{
    content: ""; position: fixed; inset: 0; pointer-events: none;
    background:
        radial-gradient(ellipse 80% 35% at 50% 0%,  rgba(140,160,220,0.14) 0%, transparent 70%),
        radial-gradient(ellipse 60% 28% at 50% 100%, rgba(100,130,200,0.10) 0%, transparent 70%);
    background-size: 100% 100%;
    animation: sk-ambient 6s ease-in-out infinite;
}}
</style>"""


_is_night = _is_night_loc(_loc["lat"], _loc["lon"])
st.markdown(weather_background_css(oc, _is_night), unsafe_allow_html=True)

_time_period = _get_time_period(_loc["lat"], _loc["lon"])
st.markdown(time_of_day_css(_time_period), unsafe_allow_html=True)
st.markdown(sidebar_animation_css(oc, _is_night, _time_period), unsafe_allow_html=True)


def fmt(value, fmt_spec, fallback="—"):
    if value is None:
        return fallback
    return f"{value:{fmt_spec}}"


# ══════════════════════════════════════════════════════════════════════════════
# Page renderers
# ══════════════════════════════════════════════════════════════════════════════

def render_overview():
    # Page header
    st.markdown(f"""
    <div class="page-header">
        <div>
            <div class="page-title">Overview</div>
            <div class="page-subtitle">Real-time indoor & outdoor conditions · live from BigQuery</div>
        </div>
        <div style="color:#8899AA; font-size:0.8rem; font-weight:600;"><i class="bi bi-broadcast"></i> Last reading {hours}h window</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Hero + Highlights row ──────────────────────────────────────────────
    hero_col, hl_col = st.columns([5, 6], gap="medium")

    # Outdoor 5-day forecast for the selected city — fetched once and reused
    # by both the hero card (today's high/low) and the forecast strip below.
    _hero_fc_days = fetch_5day_forecast(_loc["lat"], _loc["lon"])
    _today_fc = _hero_fc_days[0] if _hero_fc_days else None

    with hero_col:
        # High/low for the selected city's outdoor weather (from OWM forecast).
        # Was previously pulling from indoor sensor data — wrong for this card
        # since the hero shows OUTDOOR weather for the chosen location.
        hi = f"{_today_fc['high']:.0f}" if _today_fc else "—"
        lo = f"{_today_fc['low']:.0f}"  if _today_fc else "—"
        feels = f"Feels like {ot:.0f}°" if ot is not None else ""

        st.markdown(f"""
        <div class="hero-card">
            <span class="hero-loc"><i class="bi bi-geo-alt-fill"></i> {_loc.get("city", "Lausanne")}</span>
            <div class="hero-day">{datetime.now().strftime('%A')}</div>
            <div class="hero-date">{datetime.now().strftime('%d %b, %Y')}</div>
            <div style="display:flex; justify-content:space-between; align-items:flex-end; gap: 1rem;">
                <div>
                    <div class="hero-temp">{f'{ot:.0f}°' if ot is not None else '—'}</div>
                    <div class="hero-range">High: {hi}°  ·  Low: {lo}°</div>
                </div>
                <div style="flex-shrink:0">
                    <div class="hero-icon">{wx_icon}</div>
                    <div class="hero-cond">{oc.capitalize() or '—'}</div>
                    <div class="hero-feels">{feels}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with hl_col:
        st.markdown('<div class="section-title">Indoor Data</div>', unsafe_allow_html=True)
        r1c1, r1c2 = st.columns(2)
        r2c1, r2c2 = st.columns(2)

        # Humidity card with sparkline
        with r1c1:
            with st.container(border=True):
                st.markdown('<div class="kpi-label"><i class="bi bi-droplet-half"></i>  Humidity</div>', unsafe_allow_html=True)
                if h is not None:
                    status = '<span class="kpi-dot dot-green"></span>Good' if h >= 50 else '<span class="kpi-dot dot-yellow"></span>A bit low' if h >= 40 else '<span class="kpi-dot dot-red"></span>Too low'
                    st.markdown(f'<div class="kpi-row"><span class="kpi-num">{h:.0f}</span><span class="kpi-unit">%</span></div>', unsafe_allow_html=True)
                    if not sensor_df.empty:
                        st.plotly_chart(sparkline(sensor_df["humidity"].tolist(), "#4A8FFF", 50),
                                        use_container_width=True, config={"displayModeBar": False})
                    st.markdown(f'<div class="kpi-status" style="margin-bottom:1.1rem;">{status}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="kpi-num">—</div>', unsafe_allow_html=True)

        # TVOC card
        with r1c2:
            with st.container(border=True):
                st.markdown('<div class="kpi-label"><i class="bi bi-wind"></i>  Air Quality (TVOC)</div>', unsafe_allow_html=True)
                if tv is not None:
                    status = '<span class="kpi-dot dot-green"></span>Excellent' if tv < 65 else '<span class="kpi-dot dot-green"></span>Good' if tv < 220 else '<span class="kpi-dot dot-yellow"></span>Moderate' if tv < 660 else '<span class="kpi-dot dot-red"></span>Poor'
                    st.markdown(f'<div class="kpi-row"><span class="kpi-num">{tv:.0f}</span><span class="kpi-unit">ppb</span></div>', unsafe_allow_html=True)
                    if not sensor_df.empty:
                        st.plotly_chart(sparkline(sensor_df["tvoc"].tolist(), "#00D68F", 50),
                                        use_container_width=True, config={"displayModeBar": False})
                    st.markdown(f'<div class="kpi-status" style="margin-bottom:1.1rem;">{status}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="kpi-num">—</div>', unsafe_allow_html=True)

        # Wind card
        with r2c1:
            with st.container(border=True):
                st.markdown('<div class="kpi-label"><i class="bi bi-wind"></i>  Wind Status</div>', unsafe_allow_html=True)
                if ow is not None:
                    status = '<span class="kpi-dot dot-green"></span>Calm' if ow < 5 else '<span class="kpi-dot dot-yellow"></span>Breezy' if ow < 10 else '<span class="kpi-dot dot-red"></span>Windy'
                    st.markdown(f'<div class="kpi-row"><span class="kpi-num">{ow:.1f}</span><span class="kpi-unit">m/s</span></div>', unsafe_allow_html=True)
                    if not weather_df.empty:
                        st.plotly_chart(sparkline(weather_df["wind_speed"].tolist(), "#FFAA00", 50),
                                        use_container_width=True, config={"displayModeBar": False})
                    st.markdown(f'<div class="kpi-status" style="margin-bottom:1.1rem;">{status}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="kpi-num">—</div>', unsafe_allow_html=True)

        # eCO2 card
        with r2c2:
            with st.container(border=True):
                st.markdown('<div class="kpi-label"><i class="bi bi-cloud-fog2"></i>  eCO₂</div>', unsafe_allow_html=True)
                if co is not None:
                    status = '<span class="kpi-dot dot-green"></span>Normal' if co < 600 else '<span class="kpi-dot dot-green"></span>Good' if co < 800 else '<span class="kpi-dot dot-yellow"></span>Moderate' if co < 1000 else '<span class="kpi-dot dot-red"></span>High'
                    st.markdown(f'<div class="kpi-row"><span class="kpi-num">{co:.0f}</span><span class="kpi-unit">ppm</span></div>', unsafe_allow_html=True)
                    if not sensor_df.empty:
                        st.plotly_chart(sparkline(sensor_df["eco2"].tolist(), "#FF6B9D", 50),
                                        use_container_width=True, config={"displayModeBar": False})
                    st.markdown(f'<div class="kpi-status" style="margin-bottom:1.1rem;">{status}</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="kpi-num">—</div>', unsafe_allow_html=True)

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ── 5-day outdoor forecast ───────────────────────────────────────────
    # Reuse the data already fetched above for the hero card's high/low.
    _fc_days = _hero_fc_days

    _cond_icon = {
        "clear":        "bi-sun",
        "clouds":       "bi-cloud",
        "rain":         "bi-cloud-rain",
        "drizzle":      "bi-cloud-drizzle",
        "thunderstorm": "bi-cloud-lightning-rain",
        "snow":         "bi-cloud-snow",
        "mist":         "bi-cloud-fog",
        "fog":          "bi-cloud-fog",
        "haze":         "bi-cloud-haze",
    }

    def _fc_icon(condition: str) -> str:
        key = condition.lower()
        for k, v in _cond_icon.items():
            if k in key:
                return f'<i class="bi {v}"></i>'
        return '<i class="bi bi-cloud"></i>'

    st.markdown(f'<div class="section-title">5-Day Forecast · {_loc.get("city", "")}</div>', unsafe_allow_html=True)
    with st.container(border=True):
        if _fc_days:
            day_html = ""
            for fc in _fc_days:
                day_html += f"""
                <div class="fc-day">
                    <div class="fc-day-name">{fc.get("day", "")}</div>
                    <div class="fc-icon">{_fc_icon(fc.get("condition", ""))}</div>
                    <div class="fc-high">{fc.get("high", "—")}°</div>
                    <div class="fc-low">{fc.get("low", "—")}°</div>
                    <div class="fc-cond">{fc.get("condition", "")}</div>
                </div>"""
            st.markdown(f'<div class="fc-strip">{day_html}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:#8899AA;padding:0.8rem">No forecast data available.</div>', unsafe_allow_html=True)

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # ── Recent readings + Alerts + Sun row ──────────────────────────────
    recent_col, alerts_col = st.columns([8, 4], gap="medium")

    with recent_col:
        # Recent readings
        st.markdown('<div class="section-title">Recent Readings · Indoor Temperature</div>', unsafe_allow_html=True)
        with st.container(border=True):
            if not sensor_df.empty:
                recent = sensor_df.tail(7).copy()
                cols = st.columns(len(recent))
                for i, (_, row) in enumerate(recent.iterrows()):
                    with cols[i]:
                        ts = row["timestamp"].strftime("%H:%M")
                        temp = row["temperature"]
                        # Pick icon based on temp range
                        icon = '<i class="bi bi-thermometer-high"></i>' if temp >= 28 else '<i class="bi bi-thermometer-half"></i>' if temp >= 20 else '<i class="bi bi-thermometer-low"></i>'
                        st.markdown(f"""
                        <div class="hour-card">
                            <div class="hour-time">{ts}</div>
                            <div class="hour-icon">{icon}</div>
                            <div class="hour-temp">{temp:.1f}°</div>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("No recent sensor data.")

        st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

        # Sunrise / Sunset card
        st.markdown(f'<div class="section-title">Sun Times · {_loc.get("city", "")}</div>', unsafe_allow_html=True)
        with st.container(border=True):
            try:
                s = _astral_sun(_loc["lat"], _loc["lon"])
                sunrise_str = s["sunrise"].strftime("%H:%M")
                sunset_str = s["sunset"].strftime("%H:%M")
                day_len = s["sunset"] - s["sunrise"]
                hours_d, rem = divmod(day_len.seconds, 3600)
                mins_d = rem // 60
                length_str = f"{hours_d}h {mins_d}m"
            except Exception:
                sunrise_str = sunset_str = length_str = "—"

            st.markdown(f"""
            <div style="display:flex; align-items:center; justify-content:space-around; padding: 0.4rem 0;">
                <div class="sun-row">
                    <span class="sun-icon"><i class="bi bi-sunrise"></i></span>
                    <div>
                        <div class="sun-label">Sunrise</div>
                        <div><span class="sun-value">{sunrise_str}</span></div>
                    </div>
                </div>
                <div class="sun-row">
                    <span class="sun-icon"><i class="bi bi-sunset"></i></span>
                    <div>
                        <div class="sun-label">Sunset</div>
                        <div><span class="sun-value">{sunset_str}</span></div>
                    </div>
                </div>
                <div class="sun-row">
                    <span class="sun-icon"><i class="bi bi-clock"></i></span>
                    <div>
                        <div class="sun-label">Day Length</div>
                        <div><span class="sun-value">{length_str}</span></div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    with alerts_col:
        st.markdown('<div class="section-title">Active Alerts</div>', unsafe_allow_html=True)
        with st.container(border=True):
            alerts = []
            if t is not None and t > 30: alerts.append(('<i class="bi bi-thermometer-high"></i>', "High indoor temp", f"{t:.1f} °C"))
            if h is not None and h < 40: alerts.append(('<i class="bi bi-droplet-fill"></i>', "Low humidity", f"{h:.0f} %"))
            if tv is not None and tv >= 220: alerts.append(('<i class="bi bi-wind"></i>', "Poor air quality", f"{tv:.0f} ppb"))
            if co is not None and co >= 1000: alerts.append(('<i class="bi bi-cloud-fog2"></i>', "High eCO₂", f"{co:.0f} ppm"))

            if alerts:
                for icon, label, val in alerts:
                    st.markdown(f"""
                    <div class="alert-row">
                        <span class="alert-icon">{icon}</span> &nbsp;
                        <span class="alert-label">{label}</span>
                        <div class="alert-value">{val}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style='text-align:center; padding:2rem 0;'>
                    <div style='font-size:3rem; color:#00D68F; filter: drop-shadow(0 4px 12px rgba(0, 214, 143, 0.3));'><i class="bi bi-check-circle-fill"></i></div>
                    <div style='color:#FFFFFF; font-weight:600; margin-top:0.5rem;'>All systems nominal</div>
                    <div style='color:#8899AA; font-size:0.85rem; margin-top:0.2rem;'>No active warnings</div>
                </div>
                """, unsafe_allow_html=True)


def render_trends():
    st.markdown(f"""
    <div class="page-header">
        <div>
            <div class="page-title">Trends</div>
            <div class="page-subtitle">Historical data · last {hours}h{'' if hours < 48 else f' ({hours//24}d)'}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["Temperature & Humidity", "Air Quality", "Outdoor Weather"])

    with tab1:
        with st.container(border=True):
            if not sensor_df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=sensor_df["timestamp"], y=sensor_df["temperature"],
                    name="Temperature (°C)", line=dict(color="#E94560", width=2.5, shape="spline"),
                    fill="tozeroy", fillcolor="rgba(233, 69, 96, 0.08)",
                    hovertemplate="%{y:.1f} °C<extra>Temp</extra>"))
                fig.add_trace(go.Scatter(x=sensor_df["timestamp"], y=sensor_df["humidity"],
                    name="Humidity (%)", line=dict(color="#4488FF", width=2.5, shape="spline"), yaxis="y2",
                    hovertemplate="%{y:.0f} %<extra>Humidity</extra>"))
                layout = base_layout(380)
                layout["yaxis"] = dict(title="°C", gridcolor=GRID, linecolor=GRID, zeroline=False)
                layout["yaxis2"] = dict(title="%", overlaying="y", side="right",
                                       gridcolor=GRID, linecolor=GRID, zeroline=False)
                fig.update_layout(**layout)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("No sensor data for this time range.")

    with tab2:
        with st.container(border=True):
            if not sensor_df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=sensor_df["timestamp"], y=sensor_df["tvoc"],
                    name="TVOC (ppb)", line=dict(color="#00D68F", width=2.5, shape="spline"),
                    fill="tozeroy", fillcolor="rgba(0, 214, 143, 0.08)",
                    hovertemplate="%{y:.0f} ppb<extra>TVOC</extra>"))
                fig.add_trace(go.Scatter(x=sensor_df["timestamp"], y=sensor_df["eco2"],
                    name="eCO₂ (ppm)", line=dict(color="#FFAA00", width=2.5, shape="spline"), yaxis="y2",
                    hovertemplate="%{y:.0f} ppm<extra>eCO₂</extra>"))
                fig.add_hline(y=220, line=dict(color="#FFAA00", dash="dot", width=1),
                              annotation_text="TVOC moderate", annotation_position="top left")
                fig.add_hline(y=1000, line=dict(color="#FF4444", dash="dot", width=1), yref="y2",
                              annotation_text="CO₂ alert", annotation_position="top right")
                layout = base_layout(380)
                layout["yaxis"] = dict(title="ppb", gridcolor=GRID, linecolor=GRID, zeroline=False)
                layout["yaxis2"] = dict(title="ppm", overlaying="y", side="right",
                                       gridcolor=GRID, linecolor=GRID, zeroline=False)
                fig.update_layout(**layout)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("No air quality data for this time range.")

    with tab3:
        with st.container(border=True):
            if not weather_df.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=weather_df["timestamp"], y=weather_df["temperature"],
                    name="Outdoor Temp (°C)", line=dict(color="#E94560", width=2.5, shape="spline"),
                    hovertemplate="%{y:.1f} °C<extra>Outdoor</extra>"))
                fig.add_trace(go.Scatter(x=weather_df["timestamp"], y=weather_df["outdoor_humidity"],
                    name="Outdoor Humidity (%)", line=dict(color="#4488FF", width=2.5, shape="spline"), yaxis="y2",
                    hovertemplate="%{y:.0f} %<extra>Humidity</extra>"))
                fig.add_trace(go.Scatter(x=weather_df["timestamp"], y=weather_df["wind_speed"],
                    name="Wind (m/s)", line=dict(color="#FFAA00", width=2, dash="dot"), yaxis="y2",
                    hovertemplate="%{y:.1f} m/s<extra>Wind</extra>"))
                layout = base_layout(380)
                layout["yaxis"] = dict(title="°C", gridcolor=GRID, linecolor=GRID, zeroline=False)
                layout["yaxis2"] = dict(title="% / m/s", overlaying="y", side="right",
                                       gridcolor=GRID, linecolor=GRID, zeroline=False)
                fig.update_layout(**layout)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("No outdoor weather data for this time range.")


def render_air_quality():
    st.markdown("""
    <div class="page-header">
        <div>
            <div class="page-title">Air Quality</div>
            <div class="page-subtitle">VOC and CO₂ readings from the SGP30 sensor</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    c1, c2 = st.columns(2, gap="medium")
    with c1:
        with st.container(border=True):
            st.markdown('<div class="section-title"><i class="bi bi-wind"></i>  TVOC (Volatile Organic Compounds)</div>', unsafe_allow_html=True)
            if tv is not None:
                tv_color = "#00D68F" if tv < 220 else "#FFAA00" if tv < 660 else "#FF4444"
                tv_status = "Excellent" if tv < 65 else "Good" if tv < 220 else "Moderate" if tv < 660 else "Poor"
                st.markdown(f"""
                <div style='font-size:4rem; font-weight:800; color:{tv_color}; line-height:1; letter-spacing:-0.04em;'>
                    {tv:.0f}<span style='font-size:1.3rem; color:#8899AA; font-weight:500'> ppb</span>
                </div>
                <div style='color:{tv_color}; font-weight:700; font-size:1.1rem; margin-top:0.5rem;'>● {tv_status}</div>
                """, unsafe_allow_html=True)
                st.write("")
                st.markdown("**Reference levels:**")
                st.markdown('<ul style="list-style:none;padding-left:0;margin:0.4rem 0 0">'
                    '<li style="margin-bottom:0.45rem"><span class="kpi-dot dot-green" style="vertical-align:middle;margin-right:8px"></span>&lt; 65 ppb — Excellent</li>'
                    '<li style="margin-bottom:0.45rem"><span class="kpi-dot dot-green" style="vertical-align:middle;margin-right:8px"></span>65–220 ppb — Good</li>'
                    '<li style="margin-bottom:0.45rem"><span class="kpi-dot dot-yellow" style="vertical-align:middle;margin-right:8px"></span>220–660 ppb — Moderate</li>'
                    '<li><span class="kpi-dot dot-red" style="vertical-align:middle;margin-right:8px"></span>&gt; 660 ppb — Poor (ventilate)</li>'
                    '</ul>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="font-size:3rem; color:#8899AA">—</div>', unsafe_allow_html=True)

    with c2:
        with st.container(border=True):
            st.markdown('<div class="section-title"><i class="bi bi-cloud-fog2"></i>  eCO₂ (Equivalent CO₂)</div>', unsafe_allow_html=True)
            if co is not None:
                co_color = "#00D68F" if co < 800 else "#FFAA00" if co < 1000 else "#FF4444"
                co_status = "Normal" if co < 600 else "Good" if co < 800 else "Moderate" if co < 1000 else "High"
                st.markdown(f"""
                <div style='font-size:4rem; font-weight:800; color:{co_color}; line-height:1; letter-spacing:-0.04em;'>
                    {co:.0f}<span style='font-size:1.3rem; color:#8899AA; font-weight:500'> ppm</span>
                </div>
                <div style='color:{co_color}; font-weight:700; font-size:1.1rem; margin-top:0.5rem;'>● {co_status}</div>
                """, unsafe_allow_html=True)
                st.write("")
                st.markdown("**Reference levels:**")
                st.markdown('<ul style="list-style:none;padding-left:0;margin:0.4rem 0 0">'
                    '<li style="margin-bottom:0.45rem"><span class="kpi-dot dot-green" style="vertical-align:middle;margin-right:8px"></span>&lt; 600 ppm — Outdoor air</li>'
                    '<li style="margin-bottom:0.45rem"><span class="kpi-dot dot-green" style="vertical-align:middle;margin-right:8px"></span>600–800 ppm — Good</li>'
                    '<li style="margin-bottom:0.45rem"><span class="kpi-dot dot-yellow" style="vertical-align:middle;margin-right:8px"></span>800–1000 ppm — Moderate</li>'
                    '<li><span class="kpi-dot dot-red" style="vertical-align:middle;margin-right:8px"></span>&gt; 1000 ppm — Stuffy (ventilate)</li>'
                    '</ul>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="font-size:3rem; color:#8899AA">—</div>', unsafe_allow_html=True)

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">History</div>', unsafe_allow_html=True)
    with st.container(border=True):
        if not sensor_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=sensor_df["timestamp"], y=sensor_df["tvoc"],
                name="TVOC (ppb)", line=dict(color="#00D68F", width=2.5, shape="spline"), fill="tozeroy",
                fillcolor="rgba(0, 214, 143, 0.08)"))
            fig.add_trace(go.Scatter(x=sensor_df["timestamp"], y=sensor_df["eco2"],
                name="eCO₂ (ppm)", line=dict(color="#FFAA00", width=2.5, shape="spline"), yaxis="y2"))
            fig.add_hline(y=220, line=dict(color="#FFAA00", dash="dot", width=1),
                          annotation_text="TVOC threshold")
            fig.add_hline(y=1000, line=dict(color="#FF4444", dash="dot", width=1), yref="y2",
                          annotation_text="CO₂ threshold")
            layout = base_layout(380)
            layout["yaxis"] = dict(title="ppb", gridcolor=GRID, linecolor=GRID)
            layout["yaxis2"] = dict(title="ppm", overlaying="y", side="right",
                                   gridcolor=GRID, linecolor=GRID)
            fig.update_layout(**layout)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No air quality data for this time range.")


def render_outdoor():
    st.markdown("""
    <div class="page-header">
        <div>
            <div class="page-title">Outdoor Weather</div>
            <div class="page-subtitle">Live conditions from OpenWeatherMap</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not latest_wx:
        st.info("No outdoor weather data yet.")
        return

    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            st.markdown(f"""
            <div style='display:flex; align-items:center; gap:1.5rem'>
                <div style='font-size:5.5rem; line-height:1; color:#FFF; filter: drop-shadow(0 8px 24px rgba(255,200,100,0.2));'>{wx_icon}</div>
                <div>
                    <div style='font-size:3.8rem; font-weight:800; color:#FFF; line-height:1; letter-spacing:-0.04em;'>{ot:.1f}°<span style='font-size:1.4rem; color:#8899AA; font-weight:500'>C</span></div>
                    <div style='font-size:1.3rem; color:#FFF; font-weight:700; margin-top:0.3rem;'>{oc.capitalize()}</div>
                    <div style='color:#8899AA; font-size:0.9rem; margin-top:0.2rem'>{st.session_state["loc"]["city"]}, {st.session_state["loc"]["country"]}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.metric("Humidity", f"{oh:.0f} %" if oh is not None else "—")
        with c3:
            st.metric("Wind", f"{ow:.1f} m/s" if ow is not None else "—")

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Indoor vs Outdoor Temperature</div>', unsafe_allow_html=True)
    with st.container(border=True):
        if not sensor_df.empty and not weather_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=sensor_df["timestamp"], y=sensor_df["temperature"],
                name="Indoor (°C)", line=dict(color="#E94560", width=2.5, shape="spline"),
                fill="tozeroy", fillcolor="rgba(233, 69, 96, 0.08)"))
            fig.add_trace(go.Scatter(x=weather_df["timestamp"], y=weather_df["temperature"],
                name="Outdoor (°C)", line=dict(color="#4488FF", width=2.5, shape="spline")))
            fig.update_layout(**base_layout(360))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Need both indoor and outdoor data for comparison.")

    st.markdown('<div class="section-title">Wind & Outdoor Humidity</div>', unsafe_allow_html=True)
    with st.container(border=True):
        if not weather_df.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=weather_df["timestamp"], y=weather_df["wind_speed"],
                name="Wind (m/s)", line=dict(color="#FFAA00", width=2.5, shape="spline"), fill="tozeroy",
                fillcolor="rgba(255, 170, 0, 0.1)"))
            fig.add_trace(go.Scatter(x=weather_df["timestamp"], y=weather_df["outdoor_humidity"],
                name="Humidity (%)", line=dict(color="#4488FF", width=2.5, shape="spline"), yaxis="y2"))
            layout = base_layout(340)
            layout["yaxis"] = dict(title="m/s", gridcolor=GRID, linecolor=GRID)
            layout["yaxis2"] = dict(title="%", overlaying="y", side="right",
                                   gridcolor=GRID, linecolor=GRID)
            fig.update_layout(**layout)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No outdoor data available.")


def render_statistics():
    st.markdown("""
    <div class="page-header">
        <div>
            <div class="page-title">Statistics</div>
            <div class="page-subtitle">Daily aggregates · last 14 days</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    daily = load_daily_stats(14)
    if daily.empty:
        st.info("No daily aggregates yet.")
        return

    today_row = daily.iloc[0] if len(daily) > 0 else None
    yest_row = daily.iloc[1] if len(daily) > 1 else None
    week_avg_t = daily.head(7)["avg_t"].mean() if len(daily) >= 1 else None

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if today_row is not None:
            d = (today_row["avg_t"] - yest_row["avg_t"]) if yest_row is not None else None
            st.metric("Today's avg temp", f"{today_row['avg_t']:.1f} °C",
                      f"{d:+.1f} vs yesterday" if d is not None else None)
    with c2:
        if today_row is not None:
            st.metric("Today's range",
                      f"{today_row['max_t']:.1f}° / {today_row['min_t']:.1f}°",
                      f"{today_row['max_t'] - today_row['min_t']:.1f} °C span")
    with c3:
        if week_avg_t is not None:
            st.metric("7-day avg", f"{week_avg_t:.1f} °C")
    with c4:
        if today_row is not None:
            st.metric("Readings today", f"{int(today_row['readings']):,}")

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Daily Temperature Range</div>', unsafe_allow_html=True)
    with st.container(border=True):
        df = daily.iloc[::-1]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["day"], y=df["max_t"],
            name="Max", line=dict(color="#E94560", width=2.5),
            mode="lines+markers", marker=dict(size=8)))
        fig.add_trace(go.Scatter(x=df["day"], y=df["min_t"],
            name="Min", line=dict(color="#4488FF", width=2.5),
            mode="lines+markers", marker=dict(size=8),
            fill="tonexty", fillcolor="rgba(140, 90, 255, 0.1)"))
        fig.add_trace(go.Scatter(x=df["day"], y=df["avg_t"],
            name="Avg", line=dict(color="#C9B6FF", width=2.5, dash="dot"),
            mode="lines+markers", marker=dict(size=6)))
        fig.update_layout(**base_layout(380))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Daily Air Quality Averages</div>', unsafe_allow_html=True)
    with st.container(border=True):
        df = daily.iloc[::-1]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df["day"], y=df["avg_tvoc"],
            name="Avg TVOC (ppb)", marker_color="#00D68F",
            marker_line_width=0))
        fig.add_trace(go.Bar(x=df["day"], y=df["avg_eco2"],
            name="Avg eCO₂ (ppm)", marker_color="#FFAA00", yaxis="y2",
            marker_line_width=0))
        layout = base_layout(340)
        layout["yaxis"] = dict(title="ppb", gridcolor=GRID, linecolor=GRID)
        layout["yaxis2"] = dict(title="ppm", overlaying="y", side="right",
                               gridcolor=GRID, linecolor=GRID)
        layout["barmode"] = "group"
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Daily Summary</div>', unsafe_allow_html=True)
    with st.container(border=True):
        display = daily.copy()
        display["day"] = display["day"].dt.strftime("%a %d %b")
        display = display.rename(columns={
            "day": "Date", "min_t": "Min °C", "max_t": "Max °C", "avg_t": "Avg °C",
            "avg_h": "Humidity %", "avg_tvoc": "TVOC ppb", "avg_eco2": "eCO₂ ppm",
            "readings": "Readings",
        })
        display = display[["Date", "Min °C", "Max °C", "Avg °C", "Humidity %", "TVOC ppb", "eCO₂ ppm", "Readings"]]
        for c in ["Min °C", "Max °C", "Avg °C", "Humidity %"]:
            display[c] = display[c].round(1)
        for c in ["TVOC ppb", "eCO₂ ppm"]:
            display[c] = display[c].round(0).astype("Int64")
        st.dataframe(display, use_container_width=True, hide_index=True)


def render_location():
    cur = st.session_state["loc"]

    st.markdown(f"""
    <div class="page-header">
        <div>
            <div class="page-title">Location</div>
            <div class="page-subtitle">Choose the city for live outdoor weather</div>
        </div>
        <div style="color:#8899AA; font-size:0.8rem; font-weight:600;">
            <i class="bi bi-geo-alt-fill" style="color:#8C5AFF;"></i> {cur["city"]}, {cur["country"]}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── City preset grid ──────────────────────────────────────────────────────
    st.markdown('<div class="section-title"><i class="bi bi-grid"></i>  Quick Select</div>', unsafe_allow_html=True)
    cols = st.columns(5, gap="small")
    for i, preset in enumerate(CITY_PRESETS):
        is_active = preset["city"] == cur["city"]
        with cols[i % 5]:
            border_color = "rgba(140,90,255,0.7)" if is_active else "rgba(255,255,255,0.08)"
            bg_color = "rgba(140,90,255,0.18)" if is_active else "rgba(255,255,255,0.03)"
            label_color = "#C9B6FF" if is_active else "#8899AA"
            city_color = "#FFFFFF" if is_active else "#CCDDEE"
            st.markdown(f"""
            <div style="
                background:{bg_color}; border:1px solid {border_color};
                border-radius:14px; padding:0.9rem 0.6rem; text-align:center;
                backdrop-filter:blur(12px); margin-bottom:0.5rem;
            ">
                <div style="font-size:0.65rem; font-weight:700; color:{label_color};
                    text-transform:uppercase; letter-spacing:0.07em;">{preset["country"]}</div>
                <div style="font-size:1rem; font-weight:700; color:{city_color};
                    margin-top:0.2rem; letter-spacing:-0.01em;">{preset["city"]}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Select" if not is_active else "Active",
                         key=f"loc_{preset['city']}",
                         use_container_width=True,
                         disabled=is_active):
                st.session_state["loc"] = preset
                st.query_params["city"] = preset["city"]
                for _k in ("lat", "lon"):
                    if _k in st.query_params:
                        del st.query_params[_k]
                fetch_live_weather.clear()
                st.rerun()

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── Custom city search ────────────────────────────────────────────────────
    st.markdown('<div class="section-title"><i class="bi bi-search"></i>  Custom City</div>', unsafe_allow_html=True)
    with st.container(border=True):
        with st.form("city_search_form", clear_on_submit=False):
            _sc1, _sc2 = st.columns([4, 1], gap="small")
            with _sc1:
                _city_query = st.text_input(
                    "City name", placeholder="e.g. Amsterdam, Singapore, Sydney…",
                    label_visibility="collapsed",
                )
            with _sc2:
                _search_clicked = st.form_submit_button("Search", use_container_width=True)

        if _search_clicked and _city_query.strip():
            with st.spinner("Searching…"):
                try:
                    import requests as _req_mod
                    _geo_url = (
                        "https://api.openweathermap.org/geo/1.0/direct"
                        f"?q={_city_query.strip()}&limit=5"
                        f"&appid={os.environ.get('OPENWEATHERMAP_API_KEY','')}"
                    )
                    _geo_resp = _req_mod.get(_geo_url, timeout=6).json()
                except Exception:
                    _geo_resp = []

            if not _geo_resp:
                st.error(f"No results for '{_city_query.strip()}'")
            else:
                st.session_state["_city_candidates"] = _geo_resp

        _candidates = st.session_state.get("_city_candidates", [])
        if _candidates:
            st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)
            for _c in _candidates:
                _name    = (_c.get("local_names") or {}).get("en") or _c["name"]
                _state   = f"{_c['state']} · " if _c.get("state") else ""
                _label   = f"{_name}, {_c['country']}  —  {_state}{_c['lat']:.4f}, {_c['lon']:.4f}"
                if st.button(_label, key=f"_pick_{_c['lat']}_{_c['lon']}", use_container_width=True):
                    st.session_state["loc"] = {
                        "city": _name, "country": _c["country"],
                        "lat": str(_c["lat"]), "lon": str(_c["lon"]),
                    }
                    st.session_state.pop("_city_candidates", None)
                    st.query_params["city"] = _name
                    st.query_params["lat"]  = str(_c["lat"])
                    st.query_params["lon"]  = str(_c["lon"])
                    fetch_live_weather.clear()
                    st.rerun()

    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)

    # ── Live preview for current selection ────────────────────────────────────
    st.markdown('<div class="section-title"><i class="bi bi-broadcast"></i>  Current Conditions</div>',
                unsafe_allow_html=True)
    with st.container(border=True):
        if "error" not in _live_wx:
            m = _live_wx.get("main", {})
            w = _live_wx.get("wind", {})
            cond_str = _live_wx.get("weather", [{}])[0].get("main", "")
            desc_str = _live_wx.get("weather", [{}])[0].get("description", "").capitalize()
            lc1, lc2, lc3, lc4 = st.columns(4)
            with lc1:
                st.metric("Temperature", f"{m.get('temp'):.1f} °C")
            with lc2:
                st.metric("Feels Like", f"{m.get('feels_like'):.1f} °C")
            with lc3:
                st.metric("Humidity", f"{m.get('humidity')} %")
            with lc4:
                st.metric("Wind", f"{w.get('speed'):.1f} m/s")
            st.markdown(f"""
            <div style="color:#8899AA; font-size:0.85rem; margin-top:0.6rem;">
                {cond_icon(cond_str.lower())} &nbsp; {desc_str}
                &nbsp;·&nbsp; {cur["city"]}, {cur["country"]}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning(f"Could not fetch live weather: {_live_wx.get('error')}")


# ── Route ─────────────────────────────────────────────────────────────────────

if selected == "Overview":
    render_overview()
elif selected == "Trends":
    render_trends()
elif selected == "Air Quality":
    render_air_quality()
elif selected == "Outdoor":
    render_outdoor()
elif selected == "Statistics":
    render_statistics()
elif selected == "Location":
    render_location()

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style='text-align:center; color:#445566; font-size:0.78rem; padding-top:2rem; font-weight:500;'>
    M5Stack Core2  ·  Cloud & Advanced Analytics  ·  UNIL
</div>
""", unsafe_allow_html=True)
