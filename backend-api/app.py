import base64
import json
import struct
import socket
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file
import io

from bq_client import (
    insert_sensor_data, insert_weather_data, get_historical_data,
    get_latest_reading, get_sensor_stats_for_date,
)
from weather_client import get_current_weather, get_5day_forecast
from forecast_service import get_weather_forecast
from voice_assistant import process_voice_query, answer_question, text_to_speech, transcribe_audio, normalize_and_scale_wav
from announcement_service import generate_announcement

app = Flask(__name__)


# ── UDP Discovery ─────────────────────────────────────────────────────────────
# M5Stack broadcasts WEATHER_STATION_DISCOVER on port 5555; we reply so the
# device can find us on any LAN without hardcoded IPs.

_DISCOVERY_PORT = 5555
_DISCOVERY_MAGIC = b"WEATHER_STATION_DISCOVER"
_DISCOVERY_REPLY = b"WEATHER_STATION_HERE"

def _run_discovery_server():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass  # not available on all platforms
        sock.bind(("", _DISCOVERY_PORT))
        print(f"[DISCOVERY] UDP listener on :{_DISCOVERY_PORT}")
        while True:
            try:
                data, addr = sock.recvfrom(64)
                if data.strip() == _DISCOVERY_MAGIC:
                    sock.sendto(_DISCOVERY_REPLY, addr)
                    print(f"[DISCOVERY] Replied to {addr[0]}")
            except Exception as e:
                print(f"[DISCOVERY] recv err: {e}")
    except Exception as e:
        print(f"[DISCOVERY] Could not start UDP listener: {e}")

threading.Thread(target=_run_discovery_server, daemon=True).start()


# ── Health ────────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200


# ── Sensor Data ───────────────────────────────────────────────────────────────

@app.route('/sensor_data', methods=['POST'])
def receive_sensor_data():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Optional: Insert into bigquery
    insert_sensor_data(data)

    return jsonify({"status": "success", "message": "Sensor data received"}), 201


@app.route('/latest_reading', methods=['GET'])
def latest_reading():
    """Returns the most recent sensor reading from BigQuery."""
    reading = get_latest_reading()
    if reading:
        return jsonify(reading), 200
    return jsonify({"error": "No data available"}), 404


@app.route('/historical', methods=['GET'])
def historical_data():
    """Returns historical sensor data.
    Query params:
        hours: number of hours of history (default: 24)
    """
    hours = request.args.get('hours', 24, type=int)
    data = get_historical_data(hours=hours)
    return jsonify({"data": data, "count": len(data)}), 200


@app.route('/daily_stats', methods=['GET'])
def daily_stats():
    """Returns aggregated indoor stats for the last N days (oldest first).
    Used by the device's History screen.
    Query params:
        days: number of days to include (default: 3)
    """
    days = request.args.get('days', 3, type=int)
    today = datetime.utcnow().date()
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    results = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        label = day_names[d.weekday()]
        stats = get_sensor_stats_for_date(d.isoformat())
        if stats:
            stats["day"] = label
            results.append(stats)
        else:
            results.append({"date": d.isoformat(), "day": label, "no_data": True})
    return jsonify({"daily": results}), 200


# ── Weather ───────────────────────────────────────────────────────────────────

@app.route('/weather', methods=['GET'])
def fetch_weather():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    if not lat or not lon:
        return jsonify({"error": "lat and lon required"}), 400

    weather_info = get_current_weather(lat, lon)
    if "error" not in weather_info:
        insert_weather_data(weather_info)
    return jsonify(weather_info), 200


# ── Forecast ──────────────────────────────────────────────────────────────────

@app.route('/outdoor_forecast', methods=['GET'])
def outdoor_forecast():
    """Returns OWM's 5-day daily forecast for the given coordinates.
    Query params: lat, lon (required).
    """
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    if not lat or not lon:
        return jsonify({"error": "lat and lon required"}), 400

    result = get_5day_forecast(lat, lon)
    if "error" in result:
        return jsonify(result), 502
    return jsonify(result), 200


@app.route('/forecast', methods=['GET'])
def weather_forecast():
    """Returns SARIMA-based indoor forecast from BigQuery sensor history.
    Query params:
        metric: 'temperature' or 'humidity' (default: temperature)
        hours: forecast horizon in hours (default: 72 = 3 days)
        history_hours: how much past data to feed the model (default: 336 = 14 days)
    """
    metric = request.args.get('metric', 'temperature')
    hours = request.args.get('hours', 72, type=int)
    history_hours = request.args.get('history_hours', 336, type=int)

    if metric not in ('temperature', 'humidity'):
        return jsonify({"error": "metric must be 'temperature' or 'humidity'"}), 400

    records = get_historical_data(hours=history_hours)
    source = "indoor_sensor"

    # SARIMA needs ≥48 hourly points. If history is too sparse, fall back to mock
    # so the device still has *something* to display rather than an error screen.
    if not records or len(records) < 48:
        records = None
        source = "mock"

    result = get_weather_forecast(records=records, metric=metric, forecast_hours=hours)
    if "error" in result:
        return jsonify(result), 500

    result["source"] = source
    return jsonify(result), 200


# ── Voice Assistant ───────────────────────────────────────────────────────────

@app.route('/voice_query', methods=['POST'])
def voice_query():
    """
    Full voice pipeline: receive WAV audio, transcribe, answer, return TTS audio.

    Expects:
        - multipart/form-data with an 'audio' file field (WAV), OR
        - JSON body with 'audio_base64' containing base64-encoded WAV

    Returns:
        JSON with 'transcription', 'answer', and 'audio_base64' (base64 MP3).
    """
    audio_bytes = None

    # Option 1: multipart file upload
    if 'audio' in request.files:
        audio_bytes = request.files['audio'].read()
    # Option 2: base64 in JSON body
    elif request.is_json and request.json.get('audio_base64'):
        audio_bytes = base64.b64decode(request.json['audio_base64'])
    # Option 3: raw WAV/binary body (M5Stack sends this to avoid base64 memory overhead)
    elif request.data and request.content_type and (
            'audio' in request.content_type or 'octet-stream' in request.content_type):
        audio_bytes = request.data

    if not audio_bytes:
        return jsonify({"error": "No audio provided. Send 'audio' file or 'audio_base64' in JSON."}), 400

    # audio modes:
    #   'true'  → JSON {transcription, answer, audio_base64} (legacy, slow on M5Stack)
    #   'false' → JSON {transcription, answer} (text only, device fetches TTS separately)
    #   'raw'   → length-prefixed binary: [4-byte LE uint32 meta-len][JSON meta][WAV bytes]
    #             — combined STT+LLM+TTS in ONE call to save a network round-trip.
    audio_mode = request.args.get('audio', 'true').lower()
    vol = request.args.get('vol', default=10, type=int)

    # Device passes its current location so weather answers reflect the user's
    # selected city, not the server's default.
    lat = request.args.get('lat')
    lon = request.args.get('lon')

    try:
        if audio_mode == 'raw':
            transcription = transcribe_audio(audio_bytes)
            answer = answer_question(transcription, lat=lat, lon=lon)
            wav_bytes = text_to_speech(answer)
            if 1 <= vol <= 10:
                wav_bytes = normalize_and_scale_wav(wav_bytes, vol)
            meta = json.dumps({"transcription": transcription, "answer": answer}).encode('utf-8')
            return struct.pack('<I', len(meta)) + meta + wav_bytes, 200, {
                'Content-Type': 'application/octet-stream'
            }
        if audio_mode == 'false':
            transcription = transcribe_audio(audio_bytes)
            answer = answer_question(transcription, lat=lat, lon=lon)
            return jsonify({"transcription": transcription, "answer": answer}), 200
        result = process_voice_query(audio_bytes, lat=lat, lon=lon)
        return jsonify({
            "transcription": result["transcription"],
            "answer": result["answer"],
            "audio_base64": base64.b64encode(result["audio"]).decode("utf-8") if result["audio"] else "",
        }), 200
    except Exception as e:
        return jsonify({"error": f"Voice query failed: {str(e)}"}), 500


@app.route('/voice_answer', methods=['GET'])
def voice_answer():
    """
    Lightweight text-only query endpoint (no audio required).
    Useful for testing the query engine without microphone/speaker.

    Query params:
        q: the question text
        tts: if 'true', also return audio_base64 (default: false)
    """
    question = request.args.get('q', '')
    if not question:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    answer_text = answer_question(question)

    response = {
        "question": question,
        "answer": answer_text,
    }

    # Optionally generate TTS
    if request.args.get('tts', 'false').lower() == 'true':
        try:
            audio = text_to_speech(answer_text)
            response["audio_base64"] = base64.b64encode(audio).decode("utf-8")
        except Exception as e:
            response["tts_error"] = str(e)

    return jsonify(response), 200


@app.route('/tts', methods=['POST'])
def tts():
    """
    Convert plain text to a WAV audio file and return raw bytes.
    Used by M5Stack to fetch TTS without base64 overhead.

    Body: plain text (Content-Type: text/plain)
    Returns: raw WAV audio bytes (16kHz, 16-bit, mono)
    """
    text = request.data.decode('utf-8').strip() if request.data else ''
    if not text:
        return jsonify({"error": "No text provided"}), 400
    try:
        audio = text_to_speech(text)
        # Peak-normalize + scale on the server so the M5Stack doesn't spend
        # several seconds doing it in MicroPython. Default vol=10 = normalized to max.
        vol = request.args.get('vol', default=10, type=int)
        if 1 <= vol <= 10:
            audio = normalize_and_scale_wav(audio, vol)
        return audio, 200, {'Content-Type': 'audio/wav'}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/announcement', methods=['GET'])
def announcement():
    """
    Generates a context-aware weather announcement.
    Called by M5Stack when motion is detected (max once per hour).

    Query params:
        lat: latitude (optional, uses default from env)
        lon: longitude (optional, uses default from env)
        audio: if 'true', include base64 MP3 audio (default: true)

    Returns:
        JSON with 'text', 'alerts', 'timestamp', and optionally 'audio_base64'.
    """
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    audio_mode = request.args.get('audio', 'true').lower()
    vol = request.args.get('vol', default=10, type=int)

    result = generate_announcement(lat=lat, lon=lon)

    # 'raw' mode: return only the WAV bytes (pre-scaled to vol). One call
    # replaces the previous /announcement + /tts round-trip pair.
    if audio_mode == 'raw':
        audio = result.get("audio")
        if not audio:
            return jsonify({"error": "No audio generated"}), 500
        if 1 <= vol <= 10:
            audio = normalize_and_scale_wav(audio, vol)
        return audio, 200, {'Content-Type': 'audio/wav'}

    response = {
        "text": result["text"],
        "alerts": result["alerts"],
        "timestamp": result["timestamp"],
    }

    if audio_mode == 'true' and result.get("audio"):
        audio = result["audio"]
        if 1 <= vol <= 10:
            audio = normalize_and_scale_wav(audio, vol)
        response["audio_base64"] = base64.b64encode(audio).decode("utf-8")

    return jsonify(response), 200


# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # Intended to be run under gunicorn in Cloud Run, but allows local testing
    app.run(host='0.0.0.0', port=8080, debug=True)
