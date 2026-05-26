"""
Sensor reading module for M5Stack Core2.

Supports:
  - ENVIII sensor (SHT30) for temperature & humidity via I2C
  - TVOC/eCO2 sensor (SGP30) via I2C
  - PIR motion sensor via digital GPIO

Falls back to mock data when running off-device for testing.
"""

# ---------------------------------------------------------------------------
# Hardware detection
# ---------------------------------------------------------------------------

_HAS_HARDWARE = False

try:
    from machine import I2C, Pin
    _HAS_HARDWARE = True
except ImportError:
    pass

# I2C addresses
SHT30_ADDR = 0x44   # ENVIII temperature & humidity
SGP30_ADDR = 0x58   # Air quality sensor
PIR_PIN    = 36     # PIR motion sensor GPIO pin (M5Stack Port B)

# I2C bus (Core2 uses bus 0, SDA=21, SCL=22)
_i2c = None

def _get_i2c():
    global _i2c
    if _i2c is None and _HAS_HARDWARE:
        _i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
    return _i2c


# ---------------------------------------------------------------------------
# ENVIII Sensor — SHT30 (Temperature & Humidity)
# ---------------------------------------------------------------------------

def read_envii():
    """
    Reads temperature (°C) and humidity (%) from the ENVIII sensor (SHT30).
    Returns dict with 'temperature' and 'humidity'.
    """
    if not _HAS_HARDWARE:
        # Mock data for local testing
        return {"temperature": 22.1, "humidity": 46.5}

    try:
        i2c = _get_i2c()
        # SHT30 measurement command: high repeatability, no clock stretching
        i2c.writeto(SHT30_ADDR, bytes([0x24, 0x00]))

        import time
        time.sleep_ms(50)

        data = i2c.readfrom(SHT30_ADDR, 6)

        # Parse temperature (bytes 0-1, CRC byte 2)
        raw_temp = (data[0] << 8) | data[1]
        temperature = round(-45 + 175 * raw_temp / 65535, 1)

        # Parse humidity (bytes 3-4, CRC byte 5)
        raw_hum = (data[3] << 8) | data[4]
        humidity = round(100 * raw_hum / 65535, 1)

        return {"temperature": temperature, "humidity": humidity}

    except Exception as e:
        print("[SENSOR] ENVIII read error: {}".format(e))
        return {"temperature": None, "humidity": None}


# ---------------------------------------------------------------------------
# Air Quality Sensor — SGP30 (TVOC & eCO2)
# ---------------------------------------------------------------------------

def _sgp30_init():
    """Initializes the SGP30 sensor."""
    if not _HAS_HARDWARE:
        return
    try:
        i2c = _get_i2c()
        # Init air quality command
        i2c.writeto(SGP30_ADDR, bytes([0x20, 0x03]))
        import time
        time.sleep_ms(10)
    except Exception as e:
        print("[SENSOR] SGP30 init error: {}".format(e))

# Auto-init on import
if _HAS_HARDWARE:
    _sgp30_init()


def read_air_quality():
    """
    Reads TVOC (ppb) and eCO2 (ppm) from the SGP30 sensor.
    Returns dict with 'tvoc' and 'eco2'.
    """
    if not _HAS_HARDWARE:
        return {"tvoc": 45, "eco2": 420}

    try:
        i2c = _get_i2c()
        # Measure air quality command
        i2c.writeto(SGP30_ADDR, bytes([0x20, 0x08]))

        import time
        time.sleep_ms(50)

        data = i2c.readfrom(SGP30_ADDR, 6)

        # eCO2: bytes 0-1 (CRC byte 2)
        eco2 = (data[0] << 8) | data[1]

        # TVOC: bytes 3-4 (CRC byte 5)
        tvoc = (data[3] << 8) | data[4]

        return {"tvoc": tvoc, "eco2": eco2}

    except Exception as e:
        print("[SENSOR] SGP30 read error: {}".format(e))
        return {"tvoc": None, "eco2": None}


# ---------------------------------------------------------------------------
# PIR Motion Sensor
# ---------------------------------------------------------------------------

def read_motion():
    """
    Reads the PIR motion sensor.
    Returns True if motion is currently detected, False otherwise.
    """
    if not _HAS_HARDWARE:
        return False

    try:
        pir = Pin(PIR_PIN, Pin.IN)
        return pir.value() == 1
    except Exception as e:
        print("[SENSOR] PIR read error: {}".format(e))
        return False


# ---------------------------------------------------------------------------
# Combined reading
# ---------------------------------------------------------------------------

def read_all_sensors():
    """
    Reads all sensors and returns a combined data dictionary.

    Returns:
        dict with: temperature, humidity, tvoc, eco2, motion_active
    """
    data = read_envii()
    data.update(read_air_quality())
    data["motion_active"] = read_motion()
    return data
