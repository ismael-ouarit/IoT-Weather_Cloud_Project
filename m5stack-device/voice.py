"""
Voice interaction module for M5Stack Core2.

Handles:
  - Recording audio from the built-in microphone (PDM)
  - Sending audio to the backend for STT → Query → TTS
  - Playing the response through the built-in speaker
  - Requesting weather announcements from the backend
"""

import time

# ---------------------------------------------------------------------------
# Hardware abstraction — M5Stack Core2 mic & speaker
# ---------------------------------------------------------------------------

try:
    from m5stack import speaker
    from m5stack_ui import M5Mic
    _HAS_HARDWARE = True
except ImportError:
    _HAS_HARDWARE = False

try:
    import urequests as requests
except ImportError:
    import requests

try:
    import ujson as json
except ImportError:
    import json

try:
    import ubinascii as binascii
except ImportError:
    import base64 as binascii


# Backend URL — set this to your Cloud Run URL or local IP
API_BASE = "http://192.168.1.100:8080"  # TODO: update to your backend URL


def set_api_base(url):
    """Update the backend API base URL."""
    global API_BASE
    API_BASE = url.rstrip("/")


# ---------------------------------------------------------------------------
# Audio recording
# ---------------------------------------------------------------------------

def record_audio(duration_ms=5000, sample_rate=16000):
    """
    Records audio from the M5Stack Core2 built-in microphone.

    Args:
        duration_ms: Recording duration in milliseconds (default 5 seconds).
        sample_rate: Sample rate in Hz.

    Returns:
        bytes: WAV file content, or None if recording failed.
    """
    if not _HAS_HARDWARE:
        print("[VOICE] No hardware — cannot record audio")
        return None

    try:
        print("[VOICE] Recording for {}ms...".format(duration_ms))
        mic = M5Mic()
        mic.begin(rate=sample_rate)

        # Calculate buffer size: 16-bit mono
        num_samples = int(sample_rate * duration_ms / 1000)
        buffer = bytearray(num_samples * 2)  # 16-bit = 2 bytes per sample

        mic.record(buffer, rate=sample_rate, duration=duration_ms)
        mic.end()

        # Convert raw PCM to WAV
        wav_data = _pcm_to_wav(buffer, sample_rate, channels=1, bits=16)
        print("[VOICE] Recorded {} bytes of WAV audio".format(len(wav_data)))
        return wav_data

    except Exception as e:
        print("[VOICE] Recording error: {}".format(e))
        return None


def _pcm_to_wav(pcm_data, sample_rate, channels=1, bits=16):
    """
    Wraps raw PCM audio data in a WAV header.
    """
    import struct

    data_size = len(pcm_data)
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8

    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,        # File size - 8
        b'WAVE',
        b'fmt ',
        16,                     # Chunk size
        1,                      # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b'data',
        data_size,
    )
    return header + bytes(pcm_data)


# ---------------------------------------------------------------------------
# Voice query (send audio to backend)
# ---------------------------------------------------------------------------

def send_voice_query(wav_bytes):
    """
    Sends recorded WAV audio to the backend /voice_query endpoint.
    Returns dict with 'transcription', 'answer', and decoded MP3 audio bytes.

    Args:
        wav_bytes: WAV file content.

    Returns:
        dict with keys:
            - transcription: str
            - answer: str
            - audio: bytes (MP3) or None
        Or None on failure.
    """
    if wav_bytes is None:
        return None

    try:
        # Encode audio as base64 for JSON transport
        if hasattr(binascii, 'b2a_base64'):
            audio_b64 = binascii.b2a_base64(wav_bytes).decode('utf-8').strip()
        else:
            audio_b64 = binascii.b64encode(wav_bytes).decode('utf-8')

        url = "{}/voice_query".format(API_BASE)
        print("[VOICE] Sending query to {}...".format(url))

        response = requests.post(
            url,
            json={"audio_base64": audio_b64},
            headers={"Content-Type": "application/json"},
        )

        if response.status_code == 200:
            data = response.json()

            # Decode the MP3 audio
            audio_b64_resp = data.get("audio_base64", "")
            if audio_b64_resp:
                if hasattr(binascii, 'a2b_base64'):
                    audio_bytes = binascii.a2b_base64(audio_b64_resp)
                else:
                    audio_bytes = binascii.b64decode(audio_b64_resp)
            else:
                audio_bytes = None

            return {
                "transcription": data.get("transcription", ""),
                "answer": data.get("answer", ""),
                "audio": audio_bytes,
            }
        else:
            print("[VOICE] Server returned {}".format(response.status_code))
            return None

    except Exception as e:
        print("[VOICE] Query error: {}".format(e))
        return None


# ---------------------------------------------------------------------------
# Text-only query (no audio recording needed)
# ---------------------------------------------------------------------------

def send_text_query(question):
    """
    Sends a text question to the backend /voice_answer endpoint.
    Useful for testing without microphone.

    Returns:
        dict with 'answer' string, or None on failure.
    """
    try:
        url = "{}/voice_answer".format(API_BASE)
        response = requests.get(url, params={"q": question})
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print("[VOICE] Text query error: {}".format(e))
        return None


# ---------------------------------------------------------------------------
# Announcement (triggered on motion detection)
# ---------------------------------------------------------------------------

def request_announcement(lat=None, lon=None):
    """
    Requests a weather announcement from the backend /announcement endpoint.

    Returns:
        dict with 'text', 'alerts', 'audio' (MP3 bytes), or None on failure.
    """
    try:
        url = "{}/announcement".format(API_BASE)
        params = {}
        if lat:
            params["lat"] = lat
        if lon:
            params["lon"] = lon

        print("[VOICE] Requesting announcement from {}...".format(url))
        response = requests.get(url, params=params)

        if response.status_code == 200:
            data = response.json()

            # Decode MP3 audio
            audio_b64 = data.get("audio_base64", "")
            if audio_b64:
                if hasattr(binascii, 'a2b_base64'):
                    audio_bytes = binascii.a2b_base64(audio_b64)
                else:
                    audio_bytes = binascii.b64decode(audio_b64)
            else:
                audio_bytes = None

            return {
                "text": data.get("text", ""),
                "alerts": data.get("alerts", []),
                "audio": audio_bytes,
            }
        else:
            print("[VOICE] Announcement server returned {}".format(response.status_code))
            return None

    except Exception as e:
        print("[VOICE] Announcement error: {}".format(e))
        return None


# ---------------------------------------------------------------------------
# Audio playback
# ---------------------------------------------------------------------------

def play_audio(audio_bytes):
    """
    Plays MP3 audio through the M5Stack Core2 speaker.

    Args:
        audio_bytes: MP3 file content.
    """
    if audio_bytes is None:
        print("[VOICE] No audio to play")
        return

    if not _HAS_HARDWARE:
        print("[VOICE] Would play {} bytes of audio (no hardware)".format(len(audio_bytes)))
        return

    try:
        print("[VOICE] Playing {} bytes of audio...".format(len(audio_bytes)))
        speaker.setVolume(80)
        speaker.playWAV(audio_bytes)  # Core2 can play WAV; for MP3, use playMP3
        print("[VOICE] Playback complete")
    except Exception as e:
        print("[VOICE] Playback error: {}".format(e))


# ---------------------------------------------------------------------------
# High-level voice interaction flow
# ---------------------------------------------------------------------------

def do_voice_interaction():
    """
    Full voice interaction flow:
    1. Record audio from mic
    2. Send to backend
    3. Play the spoken answer

    Returns:
        dict with 'transcription' and 'answer', or None.
    """
    print("[VOICE] Starting voice interaction...")

    # 1. Record
    wav_data = record_audio(duration_ms=5000)
    if wav_data is None:
        print("[VOICE] Recording failed — trying text fallback")
        return None

    # 2. Send to backend
    result = send_voice_query(wav_data)
    if result is None:
        print("[VOICE] Query failed")
        return None

    print("[VOICE] Transcription: {}".format(result['transcription']))
    print("[VOICE] Answer: {}".format(result['answer']))

    # 3. Play audio response
    if result.get("audio"):
        play_audio(result["audio"])

    return result


def do_motion_announcement(lat=None, lon=None):
    """
    Triggered when motion is detected.
    Fetches and plays a weather announcement.

    Returns:
        dict with 'text' and 'alerts', or None.
    """
    print("[VOICE] Motion detected — requesting announcement...")

    result = request_announcement(lat=lat, lon=lon)
    if result is None:
        print("[VOICE] Announcement failed")
        return None

    print("[VOICE] Announcement: {}".format(result['text']))

    if result.get("audio"):
        play_audio(result["audio"])

    return result
