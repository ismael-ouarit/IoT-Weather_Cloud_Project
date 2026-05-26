"""Minimal UI test — just the display, no network/sensors."""
from m5stack import *
from m5ui import *
from uiflow import *
import math
import time

# Colors
BG = 0x1A1A2E
CARD = 0x16213E
PRIMARY = 0x0F3460
ACCENT = 0xE94560
WHITE = 0xFFFFFF
DIM = 0x8899AA
GREEN = 0x00D68F
AMBER = 0xFFAA00
RED = 0xFF4444
SUN_C = 0xFFD700
RAIN_C = 0x4488FF
CLOUD_C = 0xCCDDEE

W = 320
H = 240

def draw_sun(x, y, s=32):
    r = s // 3
    lcd.circle(x, y, r, SUN_C, SUN_C)
    rl = s // 2
    for a in range(0, 360, 45):
        ar = math.radians(a)
        lcd.line(int(x+(r+2)*math.cos(ar)), int(y+(r+2)*math.sin(ar)),
                 int(x+rl*math.cos(ar)), int(y+rl*math.sin(ar)), 0xFFA500)

def draw_cloud(x, y, s=32, c=None):
    c = c or CLOUD_C
    r = s // 4
    lcd.circle(x-r, y, r, c, c)
    lcd.circle(x+r, y, r, c, c)
    lcd.circle(x, y-r//2, int(r*1.2), c, c)
    lcd.rect(x-r-r//2, y, r*3, r, c, c)

def status_bar(title, t):
    lcd.rect(0, 0, W, 20, PRIMARY, PRIMARY)
    lcd.font(lcd.FONT_Default)
    lcd.circle(10, 10, 4, GREEN, GREEN)
    lcd.print(title, W//2 - len(title)*3, 3, WHITE)
    lcd.print(t, W-50, 3, WHITE)

def nav_bar(idx):
    y = H - 30
    lcd.rect(0, y, W, 30, BG, BG)
    for i in range(4):
        dx = W//2 - 30 + i*20
        if i == idx:
            lcd.circle(dx, y+15, 5, ACCENT, ACCENT)
        else:
            lcd.circle(dx, y+15, 3, DIM, DIM)
    lcd.rect(W//2-25, y+3, 50, 24, ACCENT, ACCENT)
    lcd.print("ASK", W//2-10, y+8, WHITE)
    if idx > 0:
        lcd.print("<", 8, y+8, DIM)
    if idx < 3:
        lcd.print(">", W-16, y+8, DIM)

def card(x, y, w, h, title=""):
    lcd.rect(x, y, w, h, CARD, CARD)
    if title:
        lcd.font(lcd.FONT_Default)
        lcd.print(title, x+8, y+4, DIM)

def home():
    lcd.clear(BG)
    status_bar("Home", "19:42")
    lcd.font(lcd.FONT_DejaVu24)
    lcd.print("19:42", W//2-40, 29, WHITE)
    lcd.font(lcd.FONT_Default)
    lcd.print("Fri 25 Apr 2026", W//2-45, 56, DIM)
    cy = 80
    card(8, cy, W//2-12, 100, "OUTDOOR")
    draw_sun(50, cy+50, 40)
    lcd.font(lcd.FONT_DejaVu24)
    lcd.print("18", 90, cy+35, WHITE)
    lcd.font(lcd.FONT_Default)
    lcd.print("C", 125, cy+35, DIM)
    lcd.print("Clear", 30, cy+78, DIM)
    card(W//2+4, cy, W//2-12, 100, "INDOOR")
    ix = W//2+20
    lcd.font(lcd.FONT_DejaVu24)
    lcd.print("22.1", ix, cy+28, WHITE)
    lcd.font(lcd.FONT_Default)
    lcd.print("C", ix+60, cy+28, DIM)
    lcd.circle(ix+75, cy+35, 4, GREEN, GREEN)
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print("46%", ix+10, cy+60, WHITE)
    lcd.font(lcd.FONT_Default)
    lcd.print("humidity", ix+10, cy+80, DIM)
    nav_bar(0)

def air():
    lcd.clear(BG)
    status_bar("Air Quality", "19:42")
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print("Indoor Air Quality", 70, 29, WHITE)
    for i, (lbl, val, mx, unit, th) in enumerate([
        ("TVOC", 45, 1000, "ppb", (65, 220)),
        ("eCO2", 420, 2000, "ppm", (600, 1000))
    ]):
        y = 54 + i * 75
        card(10, y, W-20, 65, lbl)
        bx, bw, bh = 20, W-40, 14
        lcd.rect(bx, y+22, bw, bh, 0x333344, 0x333344)
        fw = min(int((val/mx)*bw), bw)
        c = GREEN if val < th[0] else AMBER if val < th[1] else RED
        lcd.rect(bx, y+22, fw, bh, c, c)
        lcd.font(lcd.FONT_DejaVu18)
        lcd.print("{}".format(val), 20, y+42, WHITE)
        lcd.font(lcd.FONT_Default)
        lcd.print(unit, 70, y+44, DIM)
        ql = "Excellent" if val < th[0] else "Moderate" if val < th[1] else "Poor!"
        lcd.print(ql, W-70, y+44, c)
    nav_bar(1)

def forecast():
    lcd.clear(BG)
    status_bar("Forecast", "19:42")
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print("Weather Forecast", 80, 29, WHITE)
    days = [("Sat","clear",20,12),("Sun","rain",22,14),("Mon","clouds",19,11)]
    cw = 96
    for i,(d,cond,hi,lo) in enumerate(days):
        cx = 10 + i*101
        card(cx, 54, cw, 130, d)
        if cond == "clear":
            draw_sun(cx+48, 94, 30)
        elif cond == "rain":
            draw_cloud(cx+48, 88, 24, 0x778899)
            for dx2 in [-8, 0, 8]:
                lcd.line(cx+48+dx2, 102, cx+48+dx2-2, 110, RAIN_C)
        else:
            draw_cloud(cx+48, 94, 28)
        lcd.font(lcd.FONT_DejaVu18)
        lcd.print("{}".format(hi), cx+10, 124, WHITE)
        lcd.font(lcd.FONT_Default)
        lcd.print("{}".format(lo), cx+10, 146, DIM)
        lcd.print(cond, cx+8, 164, DIM)
    nav_bar(2)

def alerts():
    lcd.clear(BG)
    status_bar("Alerts", "19:42")
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print("Active Alerts", 90, 29, WHITE)
    lcd.circle(W//2, 104, 20, GREEN, GREEN)
    lcd.font(lcd.FONT_Default)
    lcd.print("OK", W//2-7, 98, WHITE)
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print("All Clear", W//2-35, 134, GREEN)
    lcd.font(lcd.FONT_Default)
    lcd.print("No active alerts", W//2-45, 159, DIM)
    nav_bar(3)

screens = [home, air, forecast, alerts]
cur = 0

# Draw initial screen
screens[cur]()

# Simple touch loop
while True:
    if touch.status():
        p = touch.read()
        x, y = p[0], p[1]
        if y > 210:
            if x < 80 and cur > 0:
                cur -= 1
                screens[cur]()
                time.sleep(0.3)
            elif x > 240 and cur < 3:
                cur += 1
                screens[cur]()
                time.sleep(0.3)
    time.sleep(0.1)
