"""Brightness test for M5Stack Core2 — 4 bars, one per method."""
from m5stack import *
from m5ui import *
from uiflow import *
from machine import I2C, Pin
import time

BG=0x1A1A2E; PRI=0x0F3460; WHT=0xFFFFFF; DIM=0x8899AA
GRN=0x00D68F; AMB=0xFFAA00; RED2=0xFF4444
W,H=320,240

# Safe brightness steps — never go to 0 so the screen stays visible
STEPS_100 = [40, 70, 100]   # 0-100 scale (Methods 1 & 3)
STEPS_12  = [5,  8,  12]    # 0-12  scale (Method 2)
STEPS_REG = [8,  12, 15]    # 0-15  LDO2 register steps (Method 4)

# Draw static layout
lcd.clear(BG)
lcd.rect(0,0,W,20,PRI,PRI)
lcd.font(lcd.FONT_Default)
lcd.print("Brightness Test — watch screen dim/brighten",4,4,WHT)

LABELS = ["1: axp(0-100)", "2: axp(0-12)", "3: lcd.setBrightness", "4: Direct I2C"]
BAR_X = 8; BAR_W = W-16; BAR_H = 18; BAR_Y0 = 30; BAR_GAP = 52

def draw_bar(i, label, val, mx, color):
    y = BAR_Y0 + i * BAR_GAP
    lcd.rect(BAR_X, y, BAR_W, BAR_H+20, BG, BG)          # clear row
    lcd.font(lcd.FONT_Default)
    lcd.print(label, BAR_X, y, DIM)
    by = y + 14
    lcd.rect(BAR_X, by, BAR_W, BAR_H, 0x333344, 0x333344) # track
    fw = int(BAR_W * val / mx)
    lcd.rect(BAR_X, by, fw, BAR_H, color, color)           # fill
    lcd.print("{}/{}".format(val, mx), BAR_X+BAR_W-40, by+3, WHT)

# ── Cycle each method through its steps ────────────────────────────────────
for step_i, (s100, s12, sreg) in enumerate(zip(STEPS_100, STEPS_12, STEPS_REG)):

    # Method 1: axp.setLcdBrightness() — 0-100 scale
    draw_bar(0, LABELS[0], s100, 100, GRN)
    try:    axp.setLcdBrightness(s100);  time.sleep_ms(700)
    except: draw_bar(0, LABELS[0]+" FAIL", s100, 100, RED2); time.sleep_ms(700)

    # Method 2: axp.setLcdBrightness() — 0-12 scale
    draw_bar(1, LABELS[1], s12, 12, AMB)
    try:    axp.setLcdBrightness(s12);   time.sleep_ms(700)
    except: draw_bar(1, LABELS[1]+" FAIL", s12, 12, RED2); time.sleep_ms(700)

    # Method 3: lcd.setBrightness() — 0-100 scale
    draw_bar(2, LABELS[2], s100, 100, GRN)
    try:    lcd.setBrightness(s100);     time.sleep_ms(700)
    except: draw_bar(2, LABELS[2]+" FAIL", s100, 100, RED2); time.sleep_ms(700)

    # Method 4: Direct AXP192 I2C register write
    draw_bar(3, LABELS[3], sreg, 15, AMB)
    try:
        i2c_axp = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
        if 0x34 in i2c_axp.scan():
            reg = i2c_axp.readfrom_mem(0x34, 0x28, 1)[0]
            i2c_axp.writeto_mem(0x34, 0x28, bytes([(sreg << 4) | (reg & 0x0F)]))
            time.sleep_ms(700)
        else:
            draw_bar(3, LABELS[3]+" NOT FOUND", sreg, 15, RED2); time.sleep_ms(700)
    except Exception as e:
        draw_bar(3, LABELS[3]+" FAIL", sreg, 15, RED2); time.sleep_ms(700)

# Restore full brightness via all methods
try:    axp.setLcdBrightness(100)
except: pass
try:    lcd.setBrightness(100)
except: pass
try:
    i2c_axp = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
    if 0x34 in i2c_axp.scan():
        reg = i2c_axp.readfrom_mem(0x34, 0x28, 1)[0]
        i2c_axp.writeto_mem(0x34, 0x28, bytes([0xF0 | (reg & 0x0F)]))
except: pass

lcd.font(lcd.FONT_Default)
lcd.print("Done — which methods dimmed the screen?", 8, H-16, DIM)
