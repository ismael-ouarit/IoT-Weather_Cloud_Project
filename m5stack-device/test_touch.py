"""Touch & button diagnostic for M5Stack Core2.

Shows raw touch.status() / touch.read() in real time and highlights
which zone (left / ask / right) would fire in the main app.
Also polls the three physical buttons as fallback.
Tap anywhere to log it. Tap the RED EXIT box to quit.
"""
from m5stack import *
from m5ui import *
from uiflow import *
import time

BG  = 0x1A1A2E
PRI = 0x0F3460
WHT = 0xFFFFFF
DIM = 0x8899AA
GRN = 0x00D68F
AMB = 0xFFAA00
RED2= 0xFF4444
ACC = 0xE94560
W, H = 320, 240

# ── draw static layout ────────────────────────────────────────────────────────

def draw_layout():
    lcd.clear(BG)
    # header
    lcd.rect(0, 0, W, 22, PRI, PRI)
    lcd.font(lcd.FONT_Default)
    lcd.print("Touch Test — tap anywhere", 10, 4, WHT)

    # zone outlines matching main-app hitboxes (y > 160)
    # left zone  x < 110
    lcd.rect(0, 160, 110, 70, 0x1A3A5A, 0x1A3A5A)
    lcd.print("LEFT", 35, 188, DIM)

    # ask zone  110 <= x <= 210
    lcd.rect(110, 160, 100, 70, 0x1A3A1A, 0x1A3A1A)
    lcd.print("ASK", 148, 188, DIM)

    # right zone  x > 210
    lcd.rect(210, 160, 110, 70, 0x3A1A1A, 0x3A1A1A)
    lcd.print("RIGHT", 240, 188, DIM)

    # exit button top-right
    lcd.rect(260, 0, 60, 22, RED2, RED2)
    lcd.print("EXIT", 270, 4, WHT)

    # section labels
    lcd.print("Last tap:", 8, 28, DIM)
    lcd.print("History (last 6):", 8, 100, DIM)
    lcd.print("Physical buttons:", 8, 140, DIM)


def clear_tap_row():
    lcd.rect(0, 44, W, 52, BG, BG)


def show_tap(x, y, zone, idx):
    """Render the most-recent tap info in the top section."""
    clear_tap_row()
    lcd.font(lcd.FONT_Default)
    color = GRN if zone != "none" else AMB
    lcd.print("x={:3d}  y={:3d}   zone: {}".format(x, y, zone), 8, 44, color)
    # crosshair dot
    if 0 <= x < W and 22 <= y < H:
        lcd.circle(x, y, 5, ACC, ACC)


history = []

def add_history(x, y, zone):
    history.insert(0, (x, y, zone))
    if len(history) > 6:
        history.pop()
    # redraw history rows
    lcd.rect(0, 110, W, 26, BG, BG)
    lcd.font(lcd.FONT_Default)
    line = "  ".join("({},{}){}".format(hx, hy, hz[0].upper()) for hx, hy, hz in history[:6])
    lcd.print(line[:52], 8, 110, DIM)


def show_btns(a, b, c):
    lcd.rect(0, 150, W, 10, BG, BG)
    lcd.font(lcd.FONT_Default)
    ca = GRN if a else DIM
    cb = GRN if b else DIM
    cc = GRN if c else DIM
    lcd.print("A", 30, 150, ca)
    lcd.print("B", 155, 150, cb)
    lcd.print("C", 280, 150, cc)


# ── classify touch zone ───────────────────────────────────────────────────────

def classify(x, y):
    # exit box
    if y < 22 and x >= 260:
        return "exit"
    if y > 160:
        if x < 110:   return "left"
        if x > 210:   return "right"
        return "ask"
    return "none"


# ── main loop ─────────────────────────────────────────────────────────────────

def run():
    draw_layout()
    last_touch = time.ticks_ms() - 500  # allow immediate first touch
    tap_idx = 0

    while True:
        # ── physical buttons ──────────────────────────────────────────────────
        try:
            a = btnA.isPressed()
            b = btnB.isPressed()
            c = btnC.isPressed()
            show_btns(a, b, c)
            if a or b or c:
                print("[BTN] A={} B={} C={}".format(a, b, c))
        except Exception as e:
            lcd.print("BTN err:"+str(e)[:20], 8, 150, RED2)

        # ── touch ─────────────────────────────────────────────────────────────
        try:
            status = touch.status()
            if status:
                p = touch.read()
                print("[RAW] status={} read={}".format(status, p))

                if p and len(p) >= 2:
                    x, y = p[0], p[1]
                    now = time.ticks_ms()
                    if time.ticks_diff(now, last_touch) >= 300:
                        last_touch = now
                        zone = classify(x, y)
                        print("[TOUCH] x={} y={}  zone={}".format(x, y, zone))
                        tap_idx += 1

                        if zone == "exit":
                            lcd.clear(BG)
                            lcd.font(lcd.FONT_Default)
                            lcd.print("Exiting test.", 60, 100, WHT)
                            time.sleep(1)
                            return

                        show_tap(x, y, zone, tap_idx)
                        add_history(x, y, zone)

                        # highlight the hit zone briefly
                        if zone == "left":
                            lcd.rect(0, 160, 110, 70, GRN, 0x1A3A5A)
                            time.sleep_ms(120)
                            lcd.rect(0, 160, 110, 70, 0x1A3A5A, 0x1A3A5A)
                            lcd.print("LEFT", 35, 188, DIM)
                        elif zone == "ask":
                            lcd.rect(110, 160, 100, 70, GRN, 0x1A3A1A)
                            time.sleep_ms(120)
                            lcd.rect(110, 160, 100, 70, 0x1A3A1A, 0x1A3A1A)
                            lcd.print("ASK", 148, 188, DIM)
                        elif zone == "right":
                            lcd.rect(210, 160, 110, 70, GRN, 0x3A1A1A)
                            time.sleep_ms(120)
                            lcd.rect(210, 160, 110, 70, 0x3A1A1A, 0x3A1A1A)
                            lcd.print("RIGHT", 240, 188, DIM)

        except Exception as e:
            print("[TOUCH] err:", e)
            lcd.font(lcd.FONT_Default)
            lcd.print("touch err:"+str(e)[:22], 8, 28, RED2)

        time.sleep_ms(20)

run()
