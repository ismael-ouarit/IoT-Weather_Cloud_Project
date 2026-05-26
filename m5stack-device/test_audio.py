"""
Audio hardware test for M5Stack Core2.
Records 3 seconds, measures mic RMS, then plays the recording back
so you can verify both mic and speaker in one shot.
"""
from m5stack import *
from m5ui import *
from uiflow import *
import math, time, struct
from machine import I2S, Pin

try:
    from m5stack import speaker
except:
    speaker = None

# --- Colors / layout ---
BG  = 0x1A1A2E
CARD= 0x16213E
PRI = 0x0F3460
WHT = 0xFFFFFF
DIM = 0x8899AA
GRN = 0x00D68F
AMB = 0xFFAA00
RED2= 0xFF4444
ACC = 0xE94560
W, H = 320, 240

WAV_PATH = '/flash/test_audio.wav'
SAMPLE_RATE = 16000
REC_MS = 3000  # 3 second recording

# ── helpers ──────────────────────────────────────────────────────────────────

def header(title):
    lcd.clear(BG)
    lcd.rect(0, 0, W, 22, PRI, PRI)
    lcd.font(lcd.FONT_Default)
    lcd.print(title, W//2 - len(title)*3, 4, WHT)

def row(y, label, msg, color):
    lcd.font(lcd.FONT_Default)
    lcd.print(label, 12, y, DIM)
    lcd.print(msg, 90, y, color)

def rms_bar(y, rms):
    max_rms = 3000
    bw = W - 24
    lcd.rect(12, y, bw, 12, CARD, CARD)
    fill = min(int(bw * rms / max_rms), bw)
    color = GRN if rms > 300 else AMB if rms > 50 else RED2
    if fill > 0:
        lcd.rect(12, y, fill, 12, color, color)
    lcd.font(lcd.FONT_Default)
    lcd.print("RMS {}".format(rms), W - 70, y, DIM)

def calc_rms(buf):
    """Return RMS of 16-bit signed PCM buffer (bytearray)."""
    n = len(buf) // 2
    if n == 0:
        return 0
    check = min(n, 4000)  # sample first 4000 frames
    total = 0
    for i in range(0, check * 2, 2):
        s = buf[i] | (buf[i + 1] << 8)
        if s > 32767:
            s -= 65536
        total += s * s
    return int((total / check) ** 0.5)

def make_wav_header(data_size, rate=16000):
    br = rate * 2
    return struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1, 1, rate, br, 2, 16,
        b'data', data_size)

# ── speaker test ─────────────────────────────────────────────────────────────

TONE_PATH = '/flash/test_tone.wav'

def make_tone_wav(freq=440, duration_ms=600, rate=16000):
    """Generate a sine-wave WAV file — speaker.tone() not available in UIFlow."""
    n = int(rate * duration_ms / 1000)
    amp = 32000
    pcm = bytearray(n * 2)
    step = 2 * math.pi * freq / rate
    for i in range(n):
        val = int(amp * math.sin(step * i))
        if val < 0:
            val += 65536
        pcm[i * 2]     = val & 0xFF
        pcm[i * 2 + 1] = (val >> 8) & 0xFF
    hdr = make_wav_header(len(pcm), rate)
    return hdr + bytes(pcm)

def test_speaker():
    header("Speaker Test")
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print("Playing tones...", 60, 60, WHT)
    lcd.font(lcd.FONT_Default)
    lcd.print("You should hear two beeps", 45, 90, DIM)

    ok = False
    err_msg = ""
    try:
        if speaker is None:
            raise Exception("no speaker module")
        # Use playWAV with a generated sine tone — avoids playTone's unknown duration unit
        for freq in (440, 880):
            wav = make_tone_wav(freq, duration_ms=400)
            with open(TONE_PATH, 'wb') as f:
                f.write(wav)
            try:
                speaker.playWAV(TONE_PATH, SAMPLE_RATE)
            except:
                speaker.playWAV(TONE_PATH)
            time.sleep_ms(300)
        ok = True
    except Exception as e:
        err_msg = str(e)
        print("[SPK] Full error:", err_msg)

    lcd.font(lcd.FONT_DejaVu18)
    if ok:
        lcd.print("Did you hear the beeps?", 30, 120, GRN)
    else:
        lcd.print("FAILED:", 12, 110, RED2)
        for i in range(3):
            chunk = err_msg[i*38:(i+1)*38]
            if chunk: lcd.font(lcd.FONT_Default); lcd.print(chunk, 12, 128+i*14, WHT)

    lcd.font(lcd.FONT_Default)
    lcd.print("Tap to continue", W//2 - 40, H - 25, DIM)
    while not touch.status():
        time.sleep(0.05)
    time.sleep_ms(300)
    return ok

# ── mic test ─────────────────────────────────────────────────────────────────

def test_mic():
    header("Mic Test  (3 s)")
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print("Get ready...", W//2 - 50, 60, DIM)
    lcd.font(lcd.FONT_Default)
    lcd.print("Recording starts after countdown", 15, 90, DIM)

    # countdown BEFORE recording so user knows when to speak
    for i in range(3, 0, -1):
        lcd.rect(W//2 - 20, 105, 40, 30, BG, BG)
        lcd.font(lcd.FONT_DejaVu24)
        lcd.print(str(i), W//2 - 8, 105, WHT)
        time.sleep(1)

    rms = 0
    pcm = None
    try:
        i2s = I2S(0, ws=Pin(0), sdin=Pin(34),
                  mode=73, dataformat=16, channelformat=4, samplerate=SAMPLE_RATE)

        # Recording has started — NOW tell the user to speak
        lcd.clear(BG)
        lcd.rect(0, 0, W, 22, 0xAA0000, 0xAA0000)
        lcd.font(lcd.FONT_Default)
        lcd.print("  REC", 4, 4, WHT)
        lcd.font(lcd.FONT_DejaVu24)
        lcd.print("SPEAK NOW!", W//2 - 65, 75, ACC)
        lcd.font(lcd.FONT_Default)
        lcd.print("Say anything for 3 seconds", 20, 120, DIM)
        num_bytes = int(SAMPLE_RATE * REC_MS / 1000) * 2
        pcm = bytearray(num_bytes)
        ptr = 0
        while ptr < num_bytes:
            n = i2s.readinto(memoryview(pcm)[ptr:])
            if n > 0:
                ptr += n
        i2s.deinit()
        rms = calc_rms(pcm)
        print("[MIC] RMS =", rms)
    except Exception as e:
        print("[MIC] Err:", e)
        lcd.print("I2S ERROR: " + str(e)[:28], 12, 130, RED2)
        lcd.print("Tap to retry", W//2 - 30, H - 25, DIM)
        while not touch.status():
            time.sleep(0.05)
        time.sleep_ms(300)
        return False, 0, None

    # Show result
    header("Mic Result")
    lcd.font(lcd.FONT_Default)
    row(35, "RMS level:", str(rms), WHT)
    rms_bar(52, rms)

    if rms > 300:
        status = "PASS - mic is working"
        color = GRN
    elif rms > 50:
        status = "WEAK - speak closer/louder"
        color = AMB
    else:
        status = "FAIL - mic appears silent"
        color = RED2

    lcd.font(lcd.FONT_DejaVu18)
    lcd.print(status, 12, 78, color)

    if pcm and rms > 50:
        try:
            # Calculate DC from stable portion — skip first 100ms PDM filter settling
            dc_start = int(SAMPLE_RATE * 0.1) * 2  # byte offset: 100ms in
            dc_end   = len(pcm)                     # use full remaining recording
            dc_end   = min(dc_end, len(pcm))
            n_dc = (dc_end - dc_start) // 2
            dc_sum = 0
            for i in range(dc_start, dc_end, 2):
                s = pcm[i] | (pcm[i+1] << 8)
                if s > 32767: s -= 65536
                dc_sum += s
            dc = dc_sum // n_dc if n_dc > 0 else 0

            # Find peak in same window after DC removal
            pk = 0
            for i in range(dc_start, dc_end, 2):
                s = pcm[i] | (pcm[i+1] << 8)
                if s > 32767: s -= 65536
                s -= dc
                s = max(-32767, min(32767, s))
                if abs(s) > pk: pk = abs(s)

            # Show 4 samples from the stable window (not startup garbage)
            vals = []
            for i in range(dc_start, dc_start + 8, 2):
                s = pcm[i] | (pcm[i+1] << 8)
                if s > 32767: s -= 65536
                vals.append(s - dc)
            lcd.font(lcd.FONT_Default)
            lcd.print("DC:{} S:{}".format(dc, vals), 12, 110, WHT)
            lcd.print("Peak(no DC): {}".format(pk), 12, 124, WHT)

            # Process pcm in-place from dc_start to end — avoids a second buffer
            gain = max(1, min(100, 32000 // (pk + 1))) if pk > 0 else 1
            for i in range(dc_start, len(pcm), 2):
                s = pcm[i] | (pcm[i+1] << 8)
                if s > 32767: s -= 65536
                s -= dc
                s = max(-32767, min(32767, s * gain))
                if s < 0: s += 65536
                pcm[i] = s & 0xFF; pcm[i+1] = (s >> 8) & 0xFF

            # Write header + processed audio in chunks (no large temp buffer)
            save_len = len(pcm) - dc_start
            dur_s = save_len // (SAMPLE_RATE * 2)
            hdr = make_wav_header(save_len)
            with open(WAV_PATH, 'wb') as f:
                f.write(hdr)
                for off in range(dc_start, len(pcm), 4096):
                    f.write(pcm[off : min(off + 4096, len(pcm))])
            lcd.print("{}s clip, DC={} x{} saved".format(dur_s, dc, gain), 12, 138, DIM)
        except Exception as e:
            lcd.print("Save err: " + str(e)[:30], 12, 110, RED2)
            print("[SAV] Err:", e); pcm = None
    else:
        lcd.font(lcd.FONT_Default)
        lcd.print("(nothing to play back)", 12, 110, DIM)

    lcd.print("Tap to continue", W//2 - 40, H - 25, DIM)
    while not touch.status():
        time.sleep(0.05)
    time.sleep_ms(300)
    return rms > 50, rms, pcm

# ── playback test ─────────────────────────────────────────────────────────────

def test_playback():
    header("Playback Test")
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print("Playing your recording...", 20, 60, WHT)
    lcd.font(lcd.FONT_Default)
    lcd.print("You should hear your own voice", 20, 90, DIM)

    ok = False
    err_msg = ""
    try:
        if speaker is None:
            raise Exception("no speaker module")
        try:
            speaker.playWAV(WAV_PATH, SAMPLE_RATE)
            ok = True
        except Exception as e1:
            print("[SPK] playWAV(path,rate) err:", e1)
            try:
                speaker.playWAV(WAV_PATH)
                ok = True
            except Exception as e2:
                err_msg = str(e2)
                print("[SPK] playWAV(path) err:", e2)
    except Exception as e:
        err_msg = str(e)
        print("[SPK] Playback err:", e)

    lcd.font(lcd.FONT_DejaVu18)
    if ok:
        lcd.print("Did you hear yourself?", 30, 130, GRN)
    else:
        lcd.print("FAILED:", 12, 120, RED2)
        for i in range(3):
            chunk = err_msg[i*38:(i+1)*38]
            if chunk: lcd.font(lcd.FONT_Default); lcd.print(chunk, 12, 136+i*14, WHT)

    lcd.font(lcd.FONT_Default)
    lcd.print("Tap to go to summary", W//2 - 50, H - 25, DIM)
    while not touch.status():
        time.sleep(0.05)
    time.sleep_ms(300)
    return ok

# ── summary ───────────────────────────────────────────────────────────────────

def show_summary(spk_ok, mic_ok, rms, playback_ok):
    header("Test Summary")
    lcd.font(lcd.FONT_Default)

    items = [
        ("Speaker tone",  spk_ok),
        ("Mic recording", mic_ok),
        ("Playback",      playback_ok),
    ]
    for i, (name, ok) in enumerate(items):
        y = 40 + i * 40
        lcd.rect(12, y, W - 24, 30, CARD, CARD)
        lcd.print(name, 20, y + 8, WHT)
        label = "PASS" if ok else "FAIL"
        color = GRN if ok else RED2
        lcd.print(label, W - 55, y + 8, color)

    lcd.font(lcd.FONT_Default)
    lcd.print("RMS = {}  (>300 great, >50 ok, <50 silent)".format(rms)[:40], 12, 165, DIM)

    if spk_ok and mic_ok and playback_ok:
        lcd.font(lcd.FONT_DejaVu18)
        lcd.print("All good! Voice query should work", 5, 185, GRN)
    elif not mic_ok:
        lcd.print("Mic is silent — check I2S wiring", 12, 185, RED2)
    elif not spk_ok:
        lcd.print("Speaker issue — check volume/module", 5, 185, AMB)

    lcd.font(lcd.FONT_Default)
    lcd.print("Tap to run again", W//2 - 40, H - 12, DIM)
    while not touch.status():
        time.sleep(0.05)
    time.sleep_ms(300)

# ── main ──────────────────────────────────────────────────────────────────────

def run():
    while True:
        spk_ok = test_speaker()
        mic_ok, rms, pcm = test_mic()
        playback_ok = False
        if mic_ok and pcm:
            playback_ok = test_playback()
        show_summary(spk_ok, mic_ok, rms, playback_ok)

run()
