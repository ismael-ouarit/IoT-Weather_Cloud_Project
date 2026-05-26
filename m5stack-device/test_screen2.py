"""
Test lcd.triangle() and lcd.line() on M5Stack Core2 via UIFlow.
"""
from m5stack import *
from m5ui import *
from uiflow import *

lcd.clear(0x1A1A2E)
lcd.font(lcd.FONT_Default)
lcd.print("Testing line + triangle", 50, 20, 0xFFFFFF)

# Test lcd.line
lcd.line(20, 60, 300, 60, 0x00FF00)
lcd.print("line() OK", 120, 70, 0x00FF00)

# Test lcd.triangle
lcd.triangle(160, 100, 120, 160, 200, 160, 0xFFD700, 0xFFD700)
lcd.print("triangle() OK", 110, 170, 0xFFD700)

# Test lcd.font sizes
try:
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print("DejaVu18 OK", 80, 200, 0x4488FF)
except:
    lcd.font(lcd.FONT_Default)
    lcd.print("DejaVu18 NOT available", 60, 200, 0xFF4444)
