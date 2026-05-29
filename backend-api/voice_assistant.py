"""
Voice Assistant Service — Speech-to-Text, Query Engine, Text-to-Speech.

Handles the full voice interaction pipeline:
1. STT:   WAV audio → Google Cloud Speech-to-Text → text transcription
2. Query: Natural language question → Gemini Flash → text answer
3. TTS:   Text answer → Google Cloud Text-to-Speech → WAV audio bytes
"""

import os
import re
import struct
from datetime import datetime, timedelta

import google.cloud.speech as speech
import google.cloud.texttospeech as texttospeech
import google.generativeai as genai
from bq_client import (
    get_latest_reading,
    get_sensor_stats_for_date,
)
from weather_client import get_current_weather, get_weather_by_city, get_5day_forecast, get_5day_forecast_by_city


# ---------------------------------------------------------------------------
# 1. Speech-to-Text  (Google Cloud)
# ---------------------------------------------------------------------------

def transcribe_audio(audio_bytes: bytes, filename: str = "recording.wav") -> str:
    """
    Transcribes WAV audio bytes using Google Cloud Speech-to-Text.

    Args:
        audio_bytes: WAV file content (16kHz, 16-bit, mono).

    Returns:
        Transcribed text string.
    """
    client = speech.SpeechClient()

    # Strip WAV header (44 bytes) to get raw PCM for Google STT
    pcm_bytes = audio_bytes[44:] if audio_bytes[:4] == b'RIFF' else audio_bytes

    # Log audio RMS so we can tell if the mic is actually capturing sound
    import struct as _struct
    samples = _struct.unpack('<' + 'h' * (len(pcm_bytes) // 2), pcm_bytes)
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5 if samples else 0
    print(f"[STT] Audio RMS={rms:.1f}  ({len(pcm_bytes)//2} samples) — "
          f"{'SILENT - mic may not be working' if rms < 50 else 'OK'}")

    audio = speech.RecognitionAudio(content=pcm_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="en-US",
        model="latest_short",       # better than command_and_search for conversational queries
        enable_automatic_punctuation=True,
        speech_contexts=[speech.SpeechContext(
            phrases=[
                "temperature", "humidity", "weather", "forecast", "air quality",
                "TVOC", "CO2", "umbrella", "rain", "outdoor", "indoor",
                "yesterday", "today", "tomorrow",
                "Madrid", "Paris", "London", "Lausanne", "Geneva",
            ],
            boost=15.0,
        )],
    )
    response = client.recognize(config=config, audio=audio)
    if response.results:
        transcript = response.results[0].alternatives[0].transcript.strip()
        confidence = response.results[0].alternatives[0].confidence
        print(f"[STT] Heard: '{transcript}'  (confidence={confidence:.2f})")
        return transcript
    print("[STT] No transcription result — audio may be silent or too noisy")
    return ""


# ---------------------------------------------------------------------------
# 2. Query Engine — gather live data, ask Gemini to answer
# ---------------------------------------------------------------------------

_PAST_KEYWORDS   = {"yesterday", "last night", "days ago"}
_FUTURE_KEYWORDS = {
    "tomorrow", "forecast", "next", "weekend", "will it", "going to",
    "this week", "later", "upcoming", "days ahead", "rest of the week",
    "next few days", "friday", "saturday", "sunday", "monday",
    "tuesday", "wednesday", "thursday",
}


def _resolve_date(text: str) -> str:
    """Extracts a date reference from text and returns YYYY-MM-DD string."""
    today = datetime.utcnow().date()
    text_lower = text.lower()

    if "yesterday" in text_lower or "last night" in text_lower:
        return (today - timedelta(days=1)).isoformat()

    m = re.search(r"(\d+)\s*days?\s*ago", text_lower)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat()

    return today.isoformat()


def _build_context(question: str, lat: str = None, lon: str = None) -> str:
    """
    Fetches sensor and weather data relevant to the question and returns a
    plain-text context block for the Gemini prompt.
    """
    q_lower = question.lower()
    parts = []

    # Always include the latest indoor reading
    reading = get_latest_reading()
    if reading:
        parts.append(
            f"Current indoor sensor data (as of {reading.get('timestamp', 'unknown')}):\n"
            f"  Temperature: {reading.get('temperature')}°C\n"
            f"  Humidity: {reading.get('humidity')}%\n"
            f"  TVOC: {reading.get('tvoc')} ppb\n"
            f"  eCO2: {reading.get('eco2')} ppm"
        )

    # Always include outdoor weather — many questions implicitly need it.
    # Caller (device) provides lat/lon; fall back to env defaults otherwise.
    lat = lat or os.environ.get("LATITUDE", "46.5197")
    lon = lon or os.environ.get("LONGITUDE", "6.6323")
    print(f"[VQ] Outdoor weather lookup: lat={lat} lon={lon}")
    w = get_current_weather(lat, lon)
    if "error" not in w:
        main = w.get("main", {})
        desc = w.get("weather", [{}])[0].get("description", "")
        parts.append(
            f"Current outdoor weather ({w.get('name', 'local')}):\n"
            f"  Temperature: {main.get('temp')}°C "
            f"(feels like {main.get('feels_like')}°C)\n"
            f"  Humidity: {main.get('humidity')}%\n"
            f"  Conditions: {desc}\n"
            f"  Wind: {w.get('wind', {}).get('speed')} m/s"
        )
    else:
        parts.append(f"Outdoor weather unavailable: {w['error']}")

    # City-specific weather — "weather in/for <City>" or "<City> weather/forecast"
    city_m = re.search(
        r'\b(?:in|for)\s+([A-Za-z][a-zA-Z\s]+?)(?:\s*[?.,!]|$)', question, re.IGNORECASE
    )
    named_city = city_m.group(1).strip() if city_m else None
    # Words that appear after a city name in natural speech and must be stripped
    # from the tail of the regex capture before sending to OWM.
    # "in Sydney going to be tomorrow" → strip "tomorrow","be","to","going" → "Sydney"
    # "in New York this weekend"       → strip "weekend","this"             → "New York"
    _CITY_TAIL_STRIP = {
        # time references
        "tomorrow", "today", "yesterday", "tonight", "now",
        "morning", "afternoon", "evening", "night",
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday", "weekend", "week",
        # verb/phrase fragments that follow city names in questions
        "going", "be", "will", "is", "are", "was", "were",
        "to", "like", "get", "look", "seem", "do",
        "this", "the", "a", "an",
    }
    _NON_CITY = {
        "tomorrow", "today", "yesterday", "tonight", "now",
        "the weekend", "the week", "this week", "next week",
        "the morning", "the evening", "the afternoon", "the future",
        "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday",
    }
    if named_city:
        # Strip non-city words from the tail one at a time.
        parts = named_city.split()
        while parts and parts[-1].lower() in _CITY_TAIL_STRIP:
            parts.pop()
        named_city = " ".join(parts) or None
    if named_city and named_city.lower() in _NON_CITY:
        print(f"[VQ] Discarding non-city match: {named_city!r}")
        named_city = None
    if named_city:
        cw = get_weather_by_city(named_city)
        if "error" not in cw:
            cm = cw.get("main", {})
            cd = cw.get("weather", [{}])[0].get("description", "")
            parts.append(
                f"Current weather in {cw.get('name', named_city)}:\n"
                f"  Temperature: {cm.get('temp')}°C "
                f"(feels like {cm.get('feels_like')}°C)\n"
                f"  Humidity: {cm.get('humidity')}%\n"
                f"  Conditions: {cd}\n"
                f"  Wind: {cw.get('wind', {}).get('speed')} m/s"
            )

    # Historical sensor stats for past-date questions
    if any(kw in q_lower for kw in _PAST_KEYWORDS):
        date_str = _resolve_date(question)
        stats = get_sensor_stats_for_date(date_str)
        if stats:
            t = stats.get("temperature", {})
            h = stats.get("humidity", {})
            parts.append(
                f"Indoor sensor data for {date_str}:\n"
                f"  Temperature: min {t.get('min')}°C, "
                f"avg {t.get('avg')}°C, max {t.get('max')}°C\n"
                f"  Humidity: min {h.get('min')}%, "
                f"avg {h.get('avg')}%, max {h.get('max')}%"
            )

    # 5-day outdoor forecast for future-weather questions.
    # If the question names a city, fetch that city's forecast; otherwise use
    # the device's current location.
    future_match = any(kw in q_lower for kw in _FUTURE_KEYWORDS)
    print(f"[VQ] q_lower={q_lower!r}  future_match={future_match}")
    if future_match:
        today = datetime.utcnow().date()
        if named_city:
            fc_result = get_5day_forecast_by_city(named_city)
            fc_label = named_city
        else:
            fc_result = get_5day_forecast(lat, lon)
            fc_label = "your location"
        if isinstance(fc_result, dict) and "error" in fc_result:
            print(f"[VQ] Forecast fetch failed: {fc_result['error']}")
        fc_days = fc_result.get("forecast", []) if isinstance(fc_result, dict) else []
        city_label = fc_result.get("city", fc_label) if isinstance(fc_result, dict) else fc_label
        print(f"[VQ] Forecast for {city_label}: {len(fc_days)} days")
        if fc_days:
            lines = [f"Outdoor forecast for {city_label} (today is {today.isoformat()}):"]
            for day in fc_days:
                # Add an explicit relative-date label so Gemini doesn't have to
                # match "tomorrow" against an absolute YYYY-MM-DD on its own.
                try:
                    fc_date = datetime.strptime(day["date"], "%Y-%m-%d").date()
                    delta = (fc_date - today).days
                    if delta == 0:    label = "today"
                    elif delta == 1:  label = "tomorrow"
                    elif delta == -1: label = "yesterday"
                    else:             label = f"in {delta} days ({day['day']})"
                except Exception:
                    label = f"{day['day']} {day['date']}"
                lines.append(
                    f"  {label} ({day['date']}): "
                    f"high {day['high']}°C, low {day['low']}°C, {day['condition']}"
                )
            parts.append("\n".join(lines))
        else:
            parts.append(f"Outdoor forecast for {fc_label} unavailable.")

    return "\n\n".join(parts) if parts else "No sensor data currently available."


_SYSTEM_PROMPT = (
    "You are a concise voice assistant built into an indoor weather station. "
    "Answer questions about indoor sensor readings, outdoor weather, air quality, and forecasts "
    "using only the data provided in the prompt. "
    "Keep every answer to 1–3 sentences — responses are read aloud via text-to-speech. "
    "Use natural conversational language. No bullet points, lists, or markdown formatting. "
    "If the context does not contain enough data to answer, say so briefly."
)


def answer_question(question: str, lat: str = None, lon: str = None) -> str:
    """
    Gathers live sensor/weather data, then uses Gemini Flash to generate
    a natural-language answer for any question phrasing.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return "Voice assistant is not configured — GEMINI_API_KEY is missing from the server environment."

    context = _build_context(question, lat=lat, lon=lon)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=_SYSTEM_PROMPT,
    )

    prompt = f"Available data:\n{context}\n\nQuestion: {question}"
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return "I ran into a problem generating an answer. Please try again."


# ---------------------------------------------------------------------------
# 3. Text-to-Speech  (Google Cloud)
# ---------------------------------------------------------------------------

def normalize_and_scale_wav(wav_bytes: bytes, vol: int) -> bytes:
    """RMS-normalize a 16-bit PCM WAV then apply gain, with hard clipping.

    Done server-side so the M5Stack doesn't have to iterate samples in slow
    MicroPython. Peak normalization alone left TTS sounding very quiet because
    a single transient spike sets the gain — most of the speech ends up far
    below max. RMS normalization brings the average loudness up; hard clipping
    on the few transients sounds fine for speech and is much louder.
    """
    if vol <= 0 or len(wav_bytes) < 44:
        return wav_bytes
    if vol > 10:
        vol = 10

    header, pcm = wav_bytes[:44], wav_bytes[44:]
    n = len(pcm) // 2
    if n == 0:
        return wav_bytes

    fmt = f"<{n}h"
    samples = struct.unpack(fmt, pcm[: n * 2])

    # RMS-based gain: target ~8000 RMS at vol=10 (loud but not destroyed).
    # For reference, int16 max is 32767; speech RMS around 6000-10000 is "loud."
    sum_sq = sum(s * s for s in samples)
    rms = (sum_sq / n) ** 0.5
    if rms < 1:
        return wav_bytes  # silent input

    target_rms = 8000 * vol / 10
    gain = target_rms / rms

    def clamp(s):
        v = int(s * gain)
        if v > 32767: return 32767
        if v < -32768: return -32768
        return v

    scaled_pcm = struct.pack(fmt, *(clamp(s) for s in samples))
    return header + scaled_pcm


def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
    """Wraps raw LINEAR16 PCM in a WAV file header."""
    channels, bits = 1, 16
    data_size = len(pcm_data)
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1, channels, sample_rate,
        byte_rate, block_align, bits,
        b'data', data_size,
    )
    return header + pcm_data


def text_to_speech(text: str, voice: str = "nova") -> bytes:
    """
    Converts text to speech using Google Cloud Text-to-Speech.

    Returns:
        WAV audio bytes (16kHz, 16-bit, mono).
    """
    client = texttospeech.TextToSpeechClient()

    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(
            language_code="en-US",
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
        ),
    )
    return _pcm_to_wav(response.audio_content, sample_rate=16000)


