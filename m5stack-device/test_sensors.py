"""Sensor test for M5Stack Core2 — direct reads, no bus scan."""
from m5stack import *
from m5ui import *
from uiflow import *
import time

BG=0x1A1A2E; PRI=0x0F3460; WHT=0xFFFFFF; DIM=0x8899AA
GRN=0x00D68F; AMB=0xFFAA00; RED2=0xFF4444
W,H=320,240

def run():
    tick=0
    sgp_init=False  # only init SGP30 once
    pir_count=0     # cumulative motion triggers across ticks
    while True:
        lcd.clear(BG)
        lcd.rect(0,0,W,22,PRI,PRI)
        lcd.font(lcd.FONT_Default)
        lcd.print("Sensor Test  tick:{}".format(tick), 20, 4, WHT)

        y=30
        lcd.print("Init I2C...", 8, y, DIM); y+=16

        try:
            from machine import I2C, Pin
            # Core2 PORT A (red Grove) = GPIO32/33, NOT 21/22 (those are internal)
            i2c=I2C(1,scl=Pin(33),sda=Pin(32),freq=100000)
            lcd.print("I2C(1) 32/33 OK", 8, y, GRN); y+=16
        except Exception as e:
            lcd.print("I2C FAIL: "+str(e)[:30], 8, y, RED2)
            lcd.print("tap to stop", 8, H-16, DIM)
            for _ in range(30):
                if touch.status(): return
                time.sleep_ms(100)
            tick+=1; continue

        # SHT40
        lcd.print("Reading SHT40...", 8, y, DIM); y+=16
        try:
            i2c.writeto(0x44, b'\xFD')
            time.sleep_ms(10)
            r=i2c.readfrom(0x44,6)
            t=round(-45+175*((r[0]<<8|r[1])/65535.0),1)
            h=round(min(100.0,100*((r[3]<<8|r[4])/65535.0)),1)
            lcd.print("SHT40 OK: T={}C H={}%".format(t,h), 8, y, GRN); y+=16
        except Exception as e:
            lcd.print("SHT40 FAIL: "+str(e)[:28], 8, y, RED2); y+=16

        # SHT30
        lcd.print("Reading SHT30...", 8, y, DIM); y+=16
        try:
            i2c.writeto(0x44, b'\x24\x00')
            time.sleep_ms(20)
            r=i2c.readfrom(0x44,6)
            t=round(-45+175*((r[0]<<8|r[1])/65535.0),1)
            h=round(min(100.0,100*((r[3]<<8|r[4])/65535.0)),1)
            lcd.print("SHT30 OK: T={}C H={}%".format(t,h), 8, y, AMB); y+=16
        except Exception as e:
            lcd.print("SHT30 FAIL: "+str(e)[:28], 8, y, DIM); y+=16

        # SGP30 on PORT C (SCL=GPIO13, SDA=GPIO14)
        # Use SoftI2C — hardware I2C(0) conflicts with UIFlow's internal touch bus
        lcd.print("Reading SGP30 (PORT C)...", 8, y, DIM); y+=16
        try:
            from machine import I2C
            i2c_c=I2C(0,scl=Pin(13),sda=Pin(14),freq=100000)
            if not sgp_init:
                i2c_c.writeto(0x58, b'\x20\x03'); time.sleep_ms(20)
                sgp_init = True
            i2c_c.writeto(0x58, b'\x20\x08'); time.sleep_ms(50)
            r=i2c_c.readfrom(0x58,6)
            eco2=(r[0]<<8|r[1]); tvoc=(r[3]<<8|r[4])
            lcd.print("SGP30 OK: CO2={}ppm TVOC={}ppb".format(eco2,tvoc), 8, y, GRN); y+=16
            if eco2==400 and tvoc==0:
                lcd.print("(warming up, normal)", 8, y, AMB); y+=16
        except Exception as e:
            lcd.print("SGP30 FAIL: "+str(e)[:28], 8, y, RED2); y+=16

        # PIR motion sensor on PORT B (GPIO36, input-only ADC pin)
        lcd.print("PIR (PORT B, GPIO36)...", 8, y, DIM); y+=16
        try:
            from machine import Pin as _Pin
            pir=_Pin(36, _Pin.IN)
            motion=pir.value()==1
            if motion: pir_count+=1
            state="MOTION!" if motion else "clear"
            color=GRN if motion else DIM
            lcd.print("PIR: {}  triggers:{}".format(state, pir_count), 8, y, color); y+=16
            # Live poll: sample GPIO36 10 times over 1s, show peak
            peak=0
            for _ in range(10):
                if pir.value()==1: peak=1
                time.sleep_ms(100)
            if peak and not motion:
                lcd.print("(blip detected in poll)", 8, y, AMB); y+=16
        except Exception as e:
            lcd.print("PIR FAIL: "+str(e)[:28], 8, y, RED2); y+=16

        lcd.print("tap to stop | refresh 3s", 8, H-16, DIM)
        # Remaining wait after the 1s PIR poll above (~2s left)
        for _ in range(20):
            if touch.status(): return
            time.sleep_ms(100)
        tick+=1

run()
