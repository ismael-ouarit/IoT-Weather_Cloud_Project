"""Diagnostic 7: 5 required args + record"""
from m5stack import *
from m5ui import *
from uiflow import *
from machine import I2S, Pin
import time, struct

lcd.clear(0x000000)
lcd.font(lcd.FONT_Default)
lcd.print("5 required args...", 5, 5, 0x00FF00)
y = 22

# 5 required: ws, mode, dataformat, channelformat, samplerate
try:
    mic = I2S(0, ws=Pin(0), sdin=Pin(34), mode=73, dataformat=16, channelformat=1, samplerate=16000)
    lcd.print("MIC OPEN!", 5, y, 0x00FF00)
    y += 16
    
    lcd.print("Recording 2s...", 5, y, 0xFFFF00)
    y += 16
    
    buf = bytearray(4096)
    n = mic.readinto(buf)
    lcd.print("Got {} bytes!".format(n), 5, y, 0x00FF00)
    y += 16
    
    # Check non-zero
    nz = sum(1 for i in range(0, min(128, len(buf)), 2) if buf[i] != 0 or buf[i+1] != 0)
    lcd.print("{}/64 non-zero samples".format(nz), 5, y, 0xFFFF00)
    y += 16
    
    # Show raw values
    vals = []
    for i in range(0, 20, 2):
        v = struct.unpack_from('<h', buf, i)[0]
        vals.append(str(v))
    lcd.print(",".join(vals[:5]), 5, y, 0xFFFF00)
    y += 16
    lcd.print(",".join(vals[5:]), 5, y, 0xFFFF00)
    
    mic.deinit()
    lcd.print("SUCCESS!", 5, y+20, 0x00FF00)
    
except Exception as e:
    lcd.print("ERR: {}".format(str(e)), 5, y, 0xFF4444)
    y += 16
    lcd.print(str(e)[30:60], 5, y, 0xFF4444)

while True:
    time.sleep(1)
