"""PIR motion sensor test for M5Stack Core2 (PORT B, GPIO36)."""
from m5stack import *
from m5ui import *
from uiflow import *
from machine import Pin
import time

BG=0x1A1A2E; PRI=0x0F3460; CARD=0x16213E
WHT=0xFFFFFF; DIM=0x8899AA; GRN=0x00D68F; AMB=0xFFAA00; RED2=0xFF4444
W,H=320,240

pir = Pin(36, Pin.IN)
triggers = 0
last_state = False

def draw_layout():
    lcd.clear(BG)
    lcd.rect(0,0,W,22,PRI,PRI)
    lcd.font(lcd.FONT_Default)
    lcd.print("PIR Test  (GPIO36 PORT B)", 20, 4, WHT)
    lcd.rect(260,0,60,22,RED2,RED2)
    lcd.print("EXIT", 270, 4, WHT)
    lcd.print("Raw GPIO36:", 8, 35, DIM)
    lcd.print("State:", 8, 55, DIM)
    lcd.print("Triggers:", 8, 75, DIM)
    lcd.print("Last 10 events:", 8, 100, DIM)
    lcd.print("Wave hand over sensor to test", 30, H-20, DIM)

history = []

def update(raw, state):
    # raw value
    lcd.rect(90, 35, 80, 14, BG, BG)
    lcd.font(lcd.FONT_Default)
    lcd.print(str(raw), 90, 35, AMB)

    # state
    lcd.rect(55, 55, W-65, 14, BG, BG)
    if state:
        lcd.rect(55, 52, 120, 18, GRN, GRN)
        lcd.print("MOTION DETECTED!", 58, 55, BG)
    else:
        lcd.rect(55, 52, 120, 18, CARD, CARD)
        lcd.print("clear", 58, 55, DIM)

    # trigger count
    lcd.rect(70, 75, 80, 14, BG, BG)
    lcd.print(str(triggers), 70, 75, WHT)

    # history log (last 10)
    lcd.rect(0, 112, W, 80, BG, BG)
    lcd.font(lcd.FONT_Default)
    for i, (ts, s) in enumerate(history[:10]):
        c = GRN if s else DIM
        lcd.print("{} {}".format(ts, "ON " if s else "OFF"), 8, 112+i*12, c)

def run():
    global triggers, last_state
    draw_layout()
    while True:
        raw = pir.value()
        state = raw == 1

        if state != last_state:
            if state:
                triggers += 1
            ts = "{:06d}ms".format(time.ticks_ms() % 1000000)
            history.insert(0, (ts, state))
            if len(history) > 10:
                history.pop()
            last_state = state

        update(raw, state)

        # exit on tap in top-right EXIT box
        try:
            if touch.status():
                p = touch.read()
                if p and p[1] < 22 and p[0] >= 260:
                    lcd.clear(BG)
                    lcd.font(lcd.FONT_Default)
                    lcd.print("Exiting.", 60, 110, WHT)
                    time.sleep(1)
                    return
        except: pass

        time.sleep_ms(50)

run()
