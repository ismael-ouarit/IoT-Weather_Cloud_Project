"""
Simple test to verify LCD drawing works on M5Stack Core2 via UIFlow.
Paste this into UIFlow Python editor and click Run.
If the screen turns dark blue with white text, the LCD API works!
"""

from m5stack import *
from m5ui import *
from uiflow import *

# Clear screen to dark blue
lcd.clear(0x1A1A2E)

# Draw a white text
lcd.font(lcd.FONT_Default)
lcd.print("Weather Station", 80, 50, 0xFFFFFF)
lcd.print("LCD Test OK!", 100, 80, 0x00FF00)

# Draw a red rectangle
lcd.rect(50, 120, 220, 40, 0xFF4444, 0xFF4444)
lcd.print("Display Working", 80, 130, 0xFFFFFF)

# Draw a circle
lcd.circle(160, 200, 15, 0xFFD700, 0xFFD700)
