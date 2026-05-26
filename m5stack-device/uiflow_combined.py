"""M5Stack Core2 Weather Station — Compact UIFlow Build"""
from m5stack import *
from m5ui import *
from uiflow import *
import math, time, json, struct, ubinascii
from machine import I2S, Pin
try:
    from m5stack import speaker
except: pass

# --- Config ---
# Discovery order: UDP broadcast → cached host → fallback IPs.
# UDP works on home LANs. Campus WiFi (AP isolation) blocks broadcast,
# so the cache (populated by UDP on home) and fallback IPs cover that case.
# Update fallback IPs here when the school IP changes — everything else is automatic.
API_PORT = 8080
_API_CACHE_FILE = "/flash/api_host.txt"  # last known good host, survives reboots
API_FALLBACKS = [
    "172.22.22.188",      # Home
    "130.223.162.219",    # School (UNIL)
]
API = ""  # set by resolve_api() at startup
TZ_OFF = 2  # UTC+2 for Switzerland (CEST)

# --- Location config ---
# LOC is mutated at boot by init_location() (auto-detect or manual override).
# Default falls back to Lausanne if both IP geolocation and stored config fail.
LOC = {"lat":"46.5197","lon":"6.6323","city":"Lausanne","mode":"default"}
LOC_FILE = "/flash/location.json"
CITY_PRESETS = [
    {"city":"Lausanne", "lat":"46.5197", "lon":"6.6323"},
    {"city":"Geneva",   "lat":"46.2044", "lon":"6.1432"},
    {"city":"Zurich",   "lat":"47.3769", "lon":"8.5417"},
    {"city":"Paris",    "lat":"48.8566", "lon":"2.3522"},
    {"city":"London",   "lat":"51.5074", "lon":"-0.1278"},
]
SENS_INT = 60   # SHT30 temp/humidity
SGP_INT  = 1    # SGP30 CO2/TVOC — datasheet requires 1Hz for baseline algorithm
PIR_INT  = 2    # PIR motion — every 2s catches any pulse
WX_INT = 300
FC_INT = 1800
HIST_INT = 1800 # daily history refresh — 30 min, data only changes daily
ANN_CD = 600    # 10 min between motion-triggered weather rundowns
ANN_BOOT_DELAY = 120  # suppress motion alerts for the first 2 min after boot
SCR_INT = 60  # Redraw screen every 60s (eliminates flickering)
VOL    = 8    # default speaker volume (0–10); overridden by load_device_settings()
BRIGHT = 3    # default brightness level 1/2/3 (dim/med/full); overridden by load_device_settings()
DEVICE_SETTINGS_FILE = "/flash/device_settings.json"

# --- Colors ---
BG=0x1A1A2E; CARD=0x16213E; PRI=0x0F3460; ACC=0xE94560
WHT=0xFFFFFF; DIM=0x8899AA; GRN=0x00D68F; AMB=0xFFAA00; RED2=0xFF4444
SUN_C=0xFFD700; RAIN_C=0x4488FF; CLD_C=0xCCDDEE
GBG=0x333344; W=320; H=240

# --- Icons ---
def draw_sun(x,y,s=32):
    r=s//3; lcd.circle(x,y,r,SUN_C,SUN_C)
    for a in range(0,360,45):
        ar=math.radians(a)
        lcd.line(int(x+(r+2)*math.cos(ar)),int(y+(r+2)*math.sin(ar)),
                 int(x+s//2*math.cos(ar)),int(y+s//2*math.sin(ar)),0xFFA500)

def draw_cloud(x,y,s=32,c=None):
    c=c or CLD_C; r=s//4
    lcd.circle(x-r,y,r,c,c); lcd.circle(x+r,y,r,c,c)
    lcd.circle(x,y-r//2,int(r*1.2),c,c); lcd.rect(x-r-r//2,y,r*3,r,c,c)

def draw_icon(cond,x,y,s=32):
    cl=cond.lower().strip()
    if 'clear' in cl or 'sun' in cl: draw_sun(x,y,s)
    elif 'rain' in cl or 'drizzle' in cl:
        draw_cloud(x,y-s//6,int(s*0.7),0x778899)
        for dx in [-s//4,0,s//4]: lcd.line(x+dx,y+s//4,x+dx-2,y+s//4+s//5,RAIN_C)
    elif 'thunder' in cl:
        draw_cloud(x,y-s//5,int(s*0.7),0x778899)
        lcd.line(x,y+s//6,x-4,y+s//6+s//4,0xFFFF00)
        lcd.line(x-4,y+s//6+s//4,x+2,y+s//6+s//4,0xFFFF00)
    elif 'snow' in cl:
        draw_cloud(x,y-s//5,int(s*0.7))
        for dx in [-s//4,0,s//4]: lcd.circle(x+dx,y+s//4,2,0xEEEEFF,0xEEEEFF)
    elif 'fog' in cl or 'mist' in cl or 'haze' in cl:
        for i in range(3):
            ly=y-s//4+i*(s//4)
            lcd.line(x-s//2,ly,x+s//2,ly,CLD_C); lcd.line(x-s//2,ly+1,x+s//2,ly+1,CLD_C)
    elif 'cloud' in cl: draw_cloud(x,y,s)
    else: draw_cloud(x,y,s)

# --- UI Helpers ---
def sbar(title,t):
    lcd.rect(0,0,W,20,PRI,PRI); lcd.font(lcd.FONT_Default)
    lcd.circle(10,10,4,GRN,GRN)
    lcd.print(title,W//2-len(title)*3,3,WHT); lcd.print(t,W-50,3,WHT)

def nbar(idx):
    y=H-30; lcd.rect(0,y,W,30,BG,BG)
    for i in range(8):
        dx=W//2-63+i*18
        if i==idx: lcd.circle(dx,y+15,5,ACC,ACC)
        else: lcd.circle(dx,y+15,3,DIM,DIM)
    if idx>0: lcd.print("<",8,y+8,DIM)
    if idx<7: lcd.print(">",W-16,y+8,DIM)

def crd(x,y,w,h,t=""):
    lcd.rect(x,y,w,h,CARD,CARD)
    if t: lcd.font(lcd.FONT_Default); lcd.print(t,x+8,y+4,DIM)

# --- Screens ---
def scr_home(d, f=True):
    if f: lcd.clear(BG)
    else: lcd.rect(0,20,W,60,BG,BG) # Clear only the time/date area
    ts=d.get("ts","--:--"); ds=d.get("ds","")
    sbar("Home",ts)
    lcd.font(lcd.FONT_DejaVu24); lcd.print(ts,W//2-40,29,WHT)
    lcd.font(lcd.FONT_Default); lcd.print(ds,W//2-45,56,DIM)
    cy=80; crd(8,cy,W//2-12,100,"OUTDOOR")
    ot=d.get("ot"); oc=d.get("oc","clear")
    oh=d.get("oh"); ow=d.get("ow")
    draw_icon(oc,28,cy+38,28)
    if ot is not None:
        lcd.font(lcd.FONT_DejaVu24); lcd.print("{}".format(int(ot)),55,cy+22,WHT)
        lcd.font(lcd.FONT_Default); lcd.print("C",90,cy+30,DIM)
    lcd.font(lcd.FONT_Default)
    if oh is not None: lcd.print("{}%".format(int(oh)),55,cy+54,DIM)
    if ow is not None: lcd.print("{}m/s".format(round(ow,1)),95,cy+54,DIM)
    lcd.print(oc[:14],10,cy+78,DIM)
    crd(W//2+4,cy,W//2-12,100,"INDOOR"); ix=W//2+20
    it=d.get("t"); ih=d.get("h"); iw=d.get("iw",0); mo=d.get("mo",False)
    if it is not None:
        lcd.font(lcd.FONT_DejaVu24); lcd.print("{}".format(round(it,1)),ix,cy+22,WHT)
        lcd.font(lcd.FONT_Default); lcd.print("C",ix+60,cy+30,DIM)
        tc=RAIN_C if it<18 else RED2 if it>28 else GRN
        lcd.circle(ix+75,cy+30,4,tc,tc)
    lcd.font(lcd.FONT_Default)
    if ih is not None:
        lcd.print("{}%".format(int(ih)),ix,cy+54,DIM)
        if ih<40: lcd.print("LOW",ix+30,cy+54,AMB)
    mc=GRN if mo else DIM; lcd.circle(W-20,cy+10,4,mc,mc)
    nbar(0)

def scr_air(d, f=True):
    if f: lcd.clear(BG)
    sbar("Air Quality",d.get("ts","--:--"))
    lcd.font(lcd.FONT_DejaVu18); lcd.print("Indoor Air Quality",70,29,WHT)
    for i,(lbl,key,mx,unit,th) in enumerate([
        ("TVOC","tv",1000,"ppb",(65,220)),("eCO2","co",2000,"ppm",(600,1000))]):
        y=54+i*75; v=d.get(key); crd(10,y,W-20,65,lbl)
        bx,bw,bh=20,W-40,14; lcd.rect(bx,y+22,bw,bh,GBG,GBG)
        if v is not None:
            fw=min(int((v/mx)*bw),bw); c=GRN if v<th[0] else AMB if v<th[1] else RED2
            lcd.rect(bx,y+22,fw,bh,c,c)
            lcd.font(lcd.FONT_DejaVu18); lcd.print("{}".format(v),20,y+42,WHT)
            lcd.font(lcd.FONT_Default); lcd.print(unit,70,y+44,DIM)
            ql="Excellent" if v<th[0] else "Moderate" if v<th[1] else "Poor!"
            lcd.print(ql,W-70,y+44,c)
    nbar(1)

def scr_owm_fc(d, f=True):
    """5-day outdoor forecast from OpenWeatherMap."""
    if f: lcd.clear(BG)
    else: lcd.rect(0,20,W,240-50,BG,BG) # Clear middle
    sbar("Outdoor",d.get("ts","--:--"))
    city=LOC.get("city","")
    title="5-Day Forecast — {}".format(city) if city else "5-Day Outdoor Forecast"
    lcd.font(lcd.FONT_DejaVu18); lcd.print(title[:34],10,29,WHT)
    fl=d.get("ofc",[])
    if not fl:
        lcd.font(lcd.FONT_Default); lcd.print("No outdoor forecast",80,100,DIM); nbar(2); return
    # 5 cards × 60px + 4 gaps × 3px + 6px left margin = 318 (2px right margin)
    cw=60
    for i,fc in enumerate(fl[:5]):
        cx=6+i*63
        crd(cx,54,cw,136,fc.get("day",""))
        draw_icon(fc.get("condition","clear"),cx+30,92,22)
        lcd.font(lcd.FONT_DejaVu18)
        lcd.print("{}".format(fc.get("high","")),cx+10,128,WHT)
        lcd.font(lcd.FONT_Default)
        lcd.print("{}".format(fc.get("low","")),cx+10,150,DIM)
        lcd.print(str(fc.get("condition",""))[:8],cx+4,170,DIM)
    nbar(2)

def scr_alert(d, f=True):
    if f: lcd.clear(BG)
    else: lcd.rect(0,20,W,240-50,BG,BG) # Clear middle
    sbar("Alerts",d.get("ts","--:--"))
    lcd.font(lcd.FONT_DejaVu18); lcd.print("Active Alerts",90,29,WHT)
    al=d.get("al",[])
    if not al:
        lcd.circle(W//2,104,20,GRN,GRN); lcd.font(lcd.FONT_Default)
        lcd.print("OK",W//2-7,98,WHT); lcd.font(lcd.FONT_DejaVu18)
        lcd.print("All Clear",W//2-35,134,GRN); lcd.font(lcd.FONT_Default)
        lcd.print("No active alerts",W//2-45,159,DIM); nbar(3); return
    for i,at in enumerate(al[:4]):
        ay=54+i*38; crd(10,ay,W-20,34,"")
        h2=int(18*0.87); lcd.triangle(28,ay+17-h2//2,28-9,ay+17+h2//2,28+9,ay+17+h2//2,AMB,AMB)
        lcd.font(lcd.FONT_Default); lcd.print(at[:38],44,ay+8,AMB)
    nbar(3)

def scr_history(d, f=True):
    """Indoor history: last 3 days of temp, humidity, air quality."""
    if f: lcd.clear(BG)
    else: lcd.rect(0,20,W,240-50,BG,BG)
    sbar("History", d.get("ts","--:--"))
    lcd.font(lcd.FONT_DejaVu18); lcd.print("Last 3 Days", 95, 29, WHT)
    daily=d.get("daily",[])
    if not daily:
        lcd.font(lcd.FONT_Default); lcd.print("Loading history...",95,110,DIM)
        nbar(4); return
    cw=100; gap=5; base_x=10
    for i,day in enumerate(daily[:3]):
        cx=base_x+i*(cw+gap)
        crd(cx,54,cw,150,"")
        # Day label (centered)
        label=day.get("day","?")
        lcd.font(lcd.FONT_DejaVu18); lcd.print(label,cx+cw//2-12,60,ACC)
        if day.get("no_data"):
            lcd.font(lcd.FONT_Default)
            lcd.print("(no data)",cx+18,110,DIM); continue
        t=day.get("temperature",{}) or {}
        h=day.get("humidity",{}) or {}
        avg_tvoc=day.get("avg_tvoc")
        # Temperature block
        lcd.font(lcd.FONT_Default); lcd.print("TEMP",cx+8,86,DIM)
        ta=t.get("avg")
        lcd.font(lcd.FONT_DejaVu18)
        lcd.print("{}C".format(ta if ta is not None else "--"),cx+8,98,WHT)
        lcd.font(lcd.FONT_Default)
        lcd.print("{}-{}".format(t.get("min","-"),t.get("max","-")),cx+8,118,DIM)
        # Humidity block
        lcd.print("HUMID",cx+8,134,DIM)
        ha=h.get("avg")
        lcd.font(lcd.FONT_DejaVu18)
        lcd.print("{}%".format(int(ha) if ha is not None else "--"),cx+8,146,WHT)
        lcd.font(lcd.FONT_Default)
        lcd.print("{}-{}".format(h.get("min","-"),h.get("max","-")),cx+8,166,DIM)
        # TVOC block
        lcd.print("TVOC",cx+8,180,DIM)
        lcd.print("{} ppb".format(int(avg_tvoc) if avg_tvoc is not None else "--"),cx+8,192,WHT)
    nbar(4)


# Y range for settings rows. Used by both the renderer and the touch handler
# so they stay in sync — change one, the other follows automatically.
_SET_ROW_Y0 = 70
_SET_ROW_H  = 22
_SET_N_ROWS = 1 + len(CITY_PRESETS)  # row 0 = "Auto", rest = city presets

def scr_settings(d, f=True):
    """Location settings: Auto-detect + manual city presets."""
    if f: lcd.clear(BG)
    sbar("Settings",d.get("ts","--:--"))
    lcd.font(lcd.FONT_DejaVu18); lcd.print("Location",110,29,WHT)
    cur_city=LOC.get("city","--"); cur_mode=LOC.get("mode","default")
    label={"auto":"Auto","manual":"Manual","default":"Default"}.get(cur_mode,cur_mode)
    lcd.font(lcd.FONT_Default)
    lcd.print("Now: {} ({})".format(cur_city,label)[:40],10,52,DIM)

    rows=[{"city":"Auto-detect (IP)"}]
    for p in CITY_PRESETS: rows.append(p)
    for i,item in enumerate(rows):
        ry=_SET_ROW_Y0+i*_SET_ROW_H
        active=(i==0 and cur_mode=="auto") or (i>0 and item.get("city")==cur_city and cur_mode=="manual")
        bg=ACC if active else CARD
        fg=WHT if active else DIM
        lcd.rect(10,ry,W-20,_SET_ROW_H-2,bg,bg)
        lcd.print(item["city"],18,ry+5,fg)
    nbar(5)


# WiFi button hit-zone — kept here so the renderer and tap handler can't drift.
_WIFI_BTN_X = 40
_WIFI_BTN_Y = 118
_WIFI_BTN_W = W - 80
_WIFI_BTN_H = 38

# Device settings hit-zones (volume row, brightness row).
# Both rows sit within y≤160 so chk_touch() treats them as body taps, not nav.
_DS_BTN_X_MINUS = 20
_DS_BTN_X_PLUS  = 245
_DS_BTN_W       = 55
_DS_BTN_H       = 24
_DS_BTN_Y_VOL   = 80    # volume ± button top edge
_DS_BRI_Y       = 126   # brightness segment row top
_DS_BRI_H       = 28    # brightness segment row height

def scr_wifi(d, f=True):
    """Network screen: shows current WiFi status and a button to re-configure."""
    if f: lcd.clear(BG)
    sbar("Network", d.get("ts","--:--"))
    lcd.font(lcd.FONT_DejaVu18); lcd.print("WiFi", 135, 29, WHT)

    ssid="(unknown)"; ip="--"; connected=False
    try:
        import network
        sta=network.WLAN(network.STA_IF)
        connected=sta.isconnected()
        if connected:
            ip=sta.ifconfig()[0]
            try: ssid=sta.config('essid')
            except:
                try: ssid=sta.config('ssid')
                except: pass
    except Exception as e: print("[WIFI] info err:",e)

    # Status card (compact — leaves room for button above nav zone)
    crd(10,56,W-20,55,"")
    sc=GRN if connected else RED2
    st="Connected" if connected else "Disconnected"
    lcd.circle(28,74,6,sc,sc)
    lcd.font(lcd.FONT_DejaVu18); lcd.print(st,42,64,WHT)
    lcd.font(lcd.FONT_Default)
    lcd.print("Network:",20,90,DIM); lcd.print(str(ssid)[:28],90,90,WHT)
    lcd.print("IP:",20,105,DIM);     lcd.print(str(ip)[:28],90,105,WHT)

    # Button is fully within body-tap zone (y < 160)
    lcd.rect(_WIFI_BTN_X,_WIFI_BTN_Y,_WIFI_BTN_W,_WIFI_BTN_H,ACC,ACC)
    lcd.font(lcd.FONT_DejaVu18)
    lcd.print("Change WiFi", _WIFI_BTN_X+_WIFI_BTN_W//2-55, _WIFI_BTN_Y+10, WHT)

    nbar(6)

def scr_device_settings(d, f=True):
    """Volume and screen-brightness controls with ± buttons and progress bars."""
    if f: lcd.clear(BG)
    sbar("Device", d.get("ts","--:--"))
    lcd.font(lcd.FONT_DejaVu18); lcd.print("Device Settings", 68, 29, WHT)

    # ── Volume ──────────────────────────────────────────────────────────────
    crd(10, 54, W-20, 52, "VOLUME")
    bw = W-40
    lcd.rect(20, 70, bw, 6, GBG, GBG)                          # track
    lcd.rect(20, 70, int(VOL/10*bw), 6, ACC, ACC)               # fill
    lcd.rect(_DS_BTN_X_MINUS, _DS_BTN_Y_VOL, _DS_BTN_W, _DS_BTN_H, ACC, ACC)
    lcd.font(lcd.FONT_DejaVu18); lcd.print("-", _DS_BTN_X_MINUS+20, _DS_BTN_Y_VOL+4, WHT)
    lcd.rect(_DS_BTN_X_PLUS,  _DS_BTN_Y_VOL, _DS_BTN_W, _DS_BTN_H, ACC, ACC)
    lcd.print("+", _DS_BTN_X_PLUS+18, _DS_BTN_Y_VOL+4, WHT)
    vc = GRN if VOL>=7 else AMB if VOL>=4 else DIM
    lcd.font(lcd.FONT_DejaVu24); lcd.print("{}/10".format(VOL), 118, _DS_BTN_Y_VOL, vc)

    # ── Brightness — 3 tappable segments ────────────────────────────────────
    crd(10, 110, W-20, 52, "BRIGHTNESS")
    _bsx = [20, 112, 204]; _bsw = 88
    for i, (sx, lbl, col) in enumerate(zip(_bsx, ["LOW", "MED", "HIGH"], [DIM, AMB, GRN])):
        active = (BRIGHT == i+1)
        bg = col if active else GBG
        fg = WHT if active else col
        lcd.rect(sx, _DS_BRI_Y, _bsw, _DS_BRI_H, bg, bg)
        lcd.font(lcd.FONT_DejaVu18)
        lcd.print(lbl, sx+16, _DS_BRI_Y+6, fg)

    nbar(7)

SCREENS=[scr_home,scr_air,scr_owm_fc,scr_alert,scr_history,scr_settings,scr_wifi,scr_device_settings]

# --- Sensors ---
_SGP_INIT=False
_i2c_a=None   # PORT A — SHT30 (I2C bus 1, GPIO32/33)
_i2c_c=None   # PORT C — SGP30 (I2C bus 0, GPIO13/14)
              # AXP192 (GPIO22/21) reuses bus 0 in _axp_set_brightness()
              # and resets _i2c_c so SGP30 re-initialises afterwards.

def _axp_set_brightness(bright):
    """Write LDO2 voltage to AXP192 register 0x28.
    Maps BRIGHT 1/2/3 → LDO2 steps 8/11/15 (~50% / 75% / 100% brightness).
    Step 8 is the lowest that keeps the LCD visibly lit; anything lower
    drops the backlight voltage below the panel's threshold (black screen).

    Uses hardware I2C(0) on GPIO22/21 — SoftI2C silently failed to write the
    AXP register. SGP30 also uses bus 0 (on different pins), so we reset
    _i2c_c after the write; SGP30's next read recreates the bus on its pins.
    """
    global _i2c_c
    _steps = {1: 8, 2: 11, 3: 15}
    ldo2 = _steps.get(bright, 15)
    try:
        from machine import I2C, Pin
        i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
        if 0x34 not in i2c.scan():
            print("[DS] AXP192 not on I2C")
            _i2c_c = None
            return False
        reg = i2c.readfrom_mem(0x34, 0x28, 1)[0]
        i2c.writeto_mem(0x34, 0x28, bytes([(ldo2 << 4) | (reg & 0x0F)]))
        print("[DS] bright={} ldo2={}".format(bright, ldo2))
        _i2c_c = None  # SGP30 must re-init bus 0 on its own pins
        return True
    except Exception as e:
        print("[DS] AXP write err:", e)
        _i2c_c = None
        return False

def _get_i2c_a():
    global _i2c_a
    if _i2c_a is None:
        from machine import I2C, Pin
        _i2c_a=I2C(1,scl=Pin(33),sda=Pin(32),freq=100000)
    return _i2c_a

def _get_i2c_c():
    global _i2c_c
    if _i2c_c is None:
        from machine import I2C, Pin
        _i2c_c=I2C(0,scl=Pin(13),sda=Pin(14),freq=100000)
    return _i2c_c

def read_sht30():
    """Read temp/humidity from SHT30 on PORT A. Called every SENS_INT (60s)."""
    try:
        i2c=_get_i2c_a()
        i2c.writeto(0x44,b'\x24\x00'); time.sleep_ms(20)
        raw=i2c.readfrom(0x44,6)
        t=round(-45+175*((raw[0]<<8|raw[1])/65535.0),1)
        h=round(min(100*((raw[3]<<8|raw[4])/65535.0),100.0),1)
        print("[SEN] SHT30: T={} H={}".format(t,h))
        return t,h
    except Exception as e:
        print("[SEN] SHT30 fail:",e)
        global _i2c_a; _i2c_a=None  # reset so next call re-creates
        return None,None

def read_sgp30():
    """Read CO2/TVOC from SGP30 on PORT C. Called every SGP_INT (1s)."""
    global _SGP_INIT
    try:
        i2c_c=_get_i2c_c()
        if not _SGP_INIT:
            i2c_c.writeto(0x58,b'\x20\x03'); time.sleep_ms(20)
            _SGP_INIT=True
            print("[SEN] SGP30 init done (warm-up ~15s)")
        i2c_c.writeto(0x58,b'\x20\x08'); time.sleep_ms(50)
        raw=i2c_c.readfrom(0x58,6)
        co=(raw[0]<<8|raw[1]); tv=(raw[3]<<8|raw[4])
        return co,tv
    except Exception as e:
        print("[SEN] SGP30 fail:",e)
        global _i2c_c; _i2c_c=None  # reset so next call re-creates
        return None,None

def read_pir():
    """Read PIR motion sensor on PORT B (GPIO36). Called every PIR_INT (2s)."""
    try:
        from machine import Pin
        return Pin(36,Pin.IN).value()==1
    except:
        return False

# --- API ---
def _req():
    try:
        import urequests as req
    except: import requests as req
    return req

# Server reachability cache — avoids any network probe when server is known down.
# None=unknown, True=reachable, False=down
_server_ok = None
_last_resolve_t = 0
_RESOLVE_CD = 60  # re-probe at most once per minute

def _tcp_ok(url, timeout=2):
    """Fast TCP connect check — no HTTP overhead, times out in `timeout` seconds."""
    s = None
    try:
        import usocket
        hp = url.split("//", 1)[1]
        host = hp.split(":")[0]
        port = int(hp.split(":")[1].split("/")[0]) if ":" in hp else 80
        ai = usocket.getaddrinfo(host, port, 0, usocket.SOCK_STREAM)
        s = usocket.socket(ai[0][0], ai[0][1], ai[0][2])
        s.settimeout(timeout)
        s.connect(ai[0][4])
        return True
    except:
        return False
    finally:
        if s:
            try: s.close()
            except: pass

def _udp_discover(port=5555, timeout=2):
    """Broadcast on the LAN and return the backend host IP, or None."""
    import usocket
    sock = None
    try:
        sock = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
        try: sock.setsockopt(usocket.SOL_SOCKET, usocket.SO_BROADCAST, 1)
        except:
            try: sock.setsockopt(1, 20, 1)  # SOL_SOCKET=1, SO_BROADCAST=20
            except: pass
        sock.settimeout(timeout)
        sock.sendto(b"WEATHER_STATION_DISCOVER", ("255.255.255.255", port))
        data, addr = sock.recvfrom(64)
        if data == b"WEATHER_STATION_HERE":
            print("[DISC] Found backend at", addr[0])
            return addr[0]
    except Exception as e:
        print("[DISC] UDP err:", e)
    finally:
        if sock:
            try: sock.close()
            except: pass
    return None

def _load_cached_host():
    try:
        with open(_API_CACHE_FILE) as f: return f.read().strip()
    except: return None

def _save_cached_host(host):
    try:
        with open(_API_CACHE_FILE, "w") as f: f.write(host)
    except Exception as e: print("[DISC] cache save err:", e)

def resolve_api():
    """Discover backend: UDP broadcast first, then cached host fallback."""
    global API, _server_ok, _last_resolve_t
    _last_resolve_t = time.time()
    # 1. UDP broadcast — finds the backend on any LAN automatically
    host = _udp_discover()
    if host:
        API = "http://{}:{}".format(host, API_PORT)
        _server_ok = True
        _save_cached_host(host)
        print("[API] Discovered:", API)
        return API
    # 2. Fall back to last known host (survives IP changes between reboots)
    cached = _load_cached_host()
    if cached:
        url = "http://{}:{}".format(cached, API_PORT)
        if _tcp_ok(url):
            API = url; _server_ok = True
            print("[API] Using cached host:", API)
            return API
    # 3. Try hardcoded fallbacks (bootstraps fresh device or empty cache)
    for host in API_FALLBACKS:
        url = "http://{}:{}".format(host, API_PORT)
        if _tcp_ok(url):
            API = url; _server_ok = True
            _save_cached_host(host)
            print("[API] Using fallback:", API)
            return API
    _server_ok = False
    print("[API] No backend found")
    return API

def _api_ready():
    """Return True if the server is (or may be) reachable. Probes only when needed."""
    global _server_ok
    # Known down and within the quiet window — return instantly, no network call
    if _server_ok is False and time.time() - _last_resolve_t < _RESOLVE_CD:
        return False
    # Unknown state OR quiet window expired — re-probe
    if _server_ok is not True:
        resolve_api()
    return _server_ok is True

def api_get(path):
    global _server_ok, _last_resolve_t
    if not _api_ready():
        return None
    req=_req()
    try:
        r=req.get("{}{}".format(API,path)); d=r.json(); r.close(); return d
    except Exception as e:
        print("[API] GET err: {}".format(e))
        _server_ok=False; _last_resolve_t=time.time(); return None

def api_post(path,data):
    global _server_ok, _last_resolve_t
    if not _api_ready():
        return None
    req=_req()
    try:
        r=req.post("{}{}".format(API,path),json=data,headers={"Content-Type":"application/json"})
        d=r.json(); r.close(); return d
    except Exception as e:
        print("[API] POST err: {}".format(e))
        _server_ok=False; _last_resolve_t=time.time(); return None

def push_data(sd):
    api_post("/sensor_data",{"temperature":sd.get("t"),"humidity":sd.get("h"),
        "tvoc":sd.get("tv"),"eco2":sd.get("co")})

def get_weather():
    d=api_get("/weather?lat={}&lon={}".format(LOC.get("lat"),LOC.get("lon")))
    if d and "error" not in d:
        m=d.get("main",{}); w=d.get("wind",{})
        return {
            "ot":m.get("temp"),
            "oh":m.get("humidity"),
            "ow":w.get("speed"),
            "oc":d.get("weather",[{}])[0].get("main","clear"),
            "od":d.get("weather",[{}])[0].get("description",""),
        }
    return {}

def get_outdoor_forecast():
    """Returns OWM 5-day daily forecast list, or [] on failure."""
    d=api_get("/outdoor_forecast?lat={}&lon={}".format(LOC.get("lat"),LOC.get("lon")))
    if not d or "forecast" not in d: return []
    return d["forecast"]

def get_daily_stats():
    """Returns last 3 days of aggregated indoor stats from BigQuery, or []."""
    d=api_get("/daily_stats?days=3")
    if not d or "daily" not in d: return []
    return d["daily"]

def get_latest_bq():
    """Fetch the most recent BigQuery sensor reading. Used at boot so the
    device displays real history immediately rather than empty placeholders.
    """
    d=api_get("/latest_reading")
    if not d or "error" in d: return None
    return d

# --- Location ---
def _load_location():
    """Read persisted location override. Returns dict or None."""
    try:
        with open(LOC_FILE) as f: return json.loads(f.read())
    except: return None

def _save_location(loc):
    try:
        with open(LOC_FILE,"w") as f: f.write(json.dumps(loc))
        return True
    except Exception as e:
        print("[LOC] save err:",e); return False

def _ip_geolocate():
    """Auto-detect via ip-api.com. Returns dict or None. ~200ms call."""
    try:
        req=_req()
        r=req.get("http://ip-api.com/json/?fields=lat,lon,city")
        d=r.json(); r.close()
        if d.get("lat") is not None and d.get("lon") is not None:
            return {"lat":str(d["lat"]),"lon":str(d["lon"]),
                    "city":d.get("city","Unknown"),"mode":"auto"}
    except Exception as e:
        print("[LOC] geo err:",e)
    return None

def init_location():
    """Called once at boot. Honors manual override if set, else auto-detects."""
    global LOC
    saved=_load_location()
    if saved and saved.get("mode")=="manual":
        LOC=saved
        print("[LOC] Manual: {} ({},{})".format(LOC["city"],LOC["lat"],LOC["lon"]))
        return
    auto=_ip_geolocate()
    if auto:
        LOC=auto; _save_location(LOC)
        print("[LOC] Auto: {} ({},{})".format(LOC["city"],LOC["lat"],LOC["lon"]))
    else:
        print("[LOC] Defaulting to {}".format(LOC["city"]))

def set_manual_city(preset):
    """Switch to a hardcoded preset city."""
    global LOC
    LOC={"lat":preset["lat"],"lon":preset["lon"],
         "city":preset["city"],"mode":"manual"}
    _save_location(LOC)
    print("[LOC] Set manual: {}".format(LOC["city"]))

def load_device_settings():
    """Load persisted volume and brightness from flash."""
    global VOL, BRIGHT
    try:
        with open(DEVICE_SETTINGS_FILE) as f:
            s = json.loads(f.read())
            VOL    = int(s.get("volume",     VOL))
            BRIGHT = max(1, min(3, int(s.get("brightness", BRIGHT))))
    except: pass

def save_device_settings():
    try:
        with open(DEVICE_SETTINGS_FILE, "w") as f:
            f.write(json.dumps({"volume": VOL, "brightness": BRIGHT}))
    except Exception as e: print("[DS] save err:", e)

def apply_device_settings():
    """Push VOL and BRIGHT to the hardware.

    Core2 backlight is on the AXP192 chip — axp.setLcdBrightness() is the
    canonical UIFlow API. lcd.setBrightness() exists on some builds but is
    often a no-op, so we try axp first and fall through if it's missing.
    """
    # Core2 setVolume() range is actually 0-11, not 0-10. Map our 0-10 UI scale
    # to 0-11 so VOL=10 gets the true hardware max (was effectively 91%).
    try:
        hw_vol = (VOL * 11 + 5) // 10 if VOL > 0 else 0
        speaker.setVolume(hw_vol)
        print("[DS] vol hw:", hw_vol)
    except Exception as e: print("[DS] vol err:", e)

    _axp_set_brightness(BRIGHT)


def set_auto_location():
    """Switch back to IP-based auto-detect."""
    global LOC
    auto=_ip_geolocate()
    if auto:
        LOC=auto; _save_location(LOC)
        print("[LOC] Re-auto: {}".format(LOC["city"]))
    else:
        # Couldn't reach ip-api.com — mark as auto so we re-probe next boot,
        # but keep current coords for now so the device still has a location.
        LOC=dict(LOC); LOC["mode"]="auto"; _save_location(LOC)

# --- Voice ---
def rec_wav_while(btn_check, max_ms=8000, min_ms=400, rt=16000):
    """Push-to-talk recorder. Records while btn_check() returns True, capped at
    max_ms so a stuck button can't lock the device. min_ms ensures we capture
    short utterances even if the user releases the button very quickly.
    """
    try:
        lcd.print("Listening...",W//2-42,130,WHT)
        # Core2 PDM mic: ws=GPIO0, sdin=GPIO34, MASTER_PDM=73
        i2s = I2S(0, ws=Pin(0), sdin=Pin(34), mode=73, dataformat=16, channelformat=4, samplerate=rt)
        chunk_ms = 100
        chunk_bytes = int(rt * chunk_ms / 1000) * 2
        max_bytes = int(rt * max_ms / 1000) * 2
        chunk = bytearray(chunk_bytes)
        b = bytearray()
        elapsed_ms = 0
        while len(b) < max_bytes:
            ptr = 0
            while ptr < chunk_bytes:
                n = i2s.readinto(memoryview(chunk)[ptr:])
                if n > 0: ptr += n
            b += chunk
            elapsed_ms += chunk_ms
            # Released early — stop, but only after the min capture window so
            # a quick tap still records something usable.
            if elapsed_ms >= min_ms and not btn_check():
                break
        i2s.deinit()
        sz = len(b); br = rt * 2
        hdr = struct.pack('<4sI4s4sIHHIIHH4sI',b'RIFF',36+sz,b'WAVE',b'fmt ',16,1,1,rt,br,2,16,b'data',sz)
        print("[MIC] Recorded {} bytes ({} ms)".format(sz, elapsed_ms))
        return hdr+b
    except Exception as e:
        print("[MIC] Err:",e)
        lcd.rect(20,50,W-40,140,CARD,CARD)
        lcd.font(lcd.FONT_Default)
        lcd.print("Mic Error:",30,70,RED2)
        lcd.print(str(e)[:30],30,90,WHT)
        time.sleep(3)
        return None

def voice_query(wav):
    """Two-call pipeline: audio→text via JSON endpoint, then text→WAV via /tts.
    Avoids urequests truncating the large binary blob returned by audio=raw.
    """
    try:
        import urequests as req
        lcd.rect(20,50,W-40,140,CARD,CARD); lcd.rect(20,50,W-40,140,PRI)
        lcd.font(lcd.FONT_Default); lcd.print("Thinking...",W//2-38,120,WHT)

        # Step 1: send audio, receive small JSON {transcription, answer}
        url = (API + "/voice_query?audio=false&lat=" + LOC["lat"] + "&lon=" + LOC["lon"])
        r = req.post(url, data=wav,
                     headers={"Content-Type":"audio/wav","Content-Length":str(len(wav))})
        if r.status_code != 200:
            print("[VQ] HTTP", r.status_code); r.close(); return "","",None
        try:
            meta = json.loads(r.content.decode('utf-8'))
        except Exception as e:
            print("[VQ] JSON err:", e); r.close(); return "","",None
        r.close()
        ans = meta.get("answer", "")
        tr  = meta.get("transcription", "")
        if not ans:
            return "", tr, None

        # Step 2: fetch TTS audio separately (raw WAV response)
        wav_audio = None
        if VOL > 0:
            try:
                body = ans.encode('utf-8')
                r2 = req.post(API + "/tts?vol=" + str(VOL), data=body,
                              headers={"Content-Type":"text/plain",
                                       "Content-Length":str(len(body))})
                if r2.status_code == 200:
                    wav_audio = r2.content
                else:
                    print("[VQ] TTS HTTP", r2.status_code)
                r2.close()
            except Exception as e:
                print("[VQ] TTS err:", e)

        return ans, tr, wav_audio
    except Exception as e: print("[VQ] Err:", e)
    return "","",None

def voice_announce():
    """Fetch the announcement WAV in a single backend call (audio=raw).
    Saves one HTTP round-trip vs the old /announcement+/tts pair.
    Returns wav_bytes or None.
    """
    if not _api_ready(): return None
    try:
        import urequests as req
        r=req.get(API+"/announcement?audio=raw&vol={}&lat={}&lon={}".format(
            VOL, LOC.get("lat"), LOC.get("lon")))
        if r.status_code!=200:
            print("[ANN] HTTP",r.status_code); r.close(); return None
        aud=r.content; r.close()
        return aud
    except Exception as e: print("[ANN] Err:",e)
    return None

# --- LED ---
def _update_led(al):
    try:
        hum = any("humidity" in a.lower() for a in al)
        co2 = any("CO2" in a or "TVOC" in a for a in al)
        if co2:
            rgb.setColorAll(0x800080)   # purple — CO2/TVOC air quality alert
        elif hum:
            rgb.setColorAll(0xFF0000)   # red — humidity alert
        else:
            rgb.setColorAll(0x000000)   # off — all clear
    except Exception as e:
        print("[LED] Err:", e)

# --- Alerts ---
def gen_alerts(sd,wx):
    al=[]
    h=sd.get("h",50)
    if h<50: al.append("Low humidity: {}%".format(int(h)))
    tv=sd.get("tv",0)
    if tv>=220: al.append("Poor air: TVOC {} ppb".format(tv))
    elif tv>=65: al.append("Moderate air: TVOC {} ppb".format(tv))
    co=sd.get("co",0)
    if co>=1000: al.append("High CO2: {} ppm".format(co))
    t2=sd.get("t",22)
    if t2>30: al.append("High temp: {}C".format(t2))
    oc=wx.get("oc","")
    if "rain" in oc.lower(): al.append("Rain outside")
    return al

NTP_CLIENT = None

# --- NTP ---
def sync_ntp():
    global NTP_CLIENT
    # Core2 has 2 clocks. We try every known UIFlow 1.x NTP method.
    # Capped at 3 retries × 1s so the device boots in under 3s if NTP is unreachable.
    # The clock will just show "--:--" until a later get_ts() lookup succeeds.
    for i in range(3):
        try:
            try:
                import ntptime
                NTP_CLIENT = ntptime.client(host='pool.ntp.org', timezone=TZ_OFF)
            except: pass
            
            try: rtc.settime('ntp', host='pool.ntp.org', tzone=TZ_OFF)
            except: pass
            
            try:
                import ntptime
                ntptime.host = "pool.ntp.org"
                ntptime.settime()
            except: pass

            # Verify if the hardware clock actually synced
            if time.localtime()[0] > 2020:
                print("[NTP] Hardware RTC synced successfully")
                return
            elif NTP_CLIENT is not None:
                ts = NTP_CLIENT.formatDatetime('-', ':')
                if ts and "2000" not in ts:
                    print("[NTP] Software RTC synced successfully")
                    return
        except Exception:
            pass
        time.sleep(1)
    print("[NTP] Failed to sync after 3 retries")

def get_ts():
    global NTP_CLIENT
    try:
        t = time.localtime()
        # If the hardware RTC synced properly (year > 2020)
        if t[0] > 2020:
            ts = "{:02d}:{:02d}".format(t[3],t[4])
            dn = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
            mn = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            ds = "{} {:02d} {} {}".format(dn[t[6]], t[2], mn[t[1]-1], t[0])
            return ts, ds
            
        # Fallback: Hardware RTC failed, but Software RTC (ntp client) might have synced
        if NTP_CLIENT is not None:
            s = NTP_CLIENT.formatDatetime('-', ':') # "YYYY-MM-DD HH:MM:SS"
            d_part, t_part = s.split(' ')
            y, m, d = d_part.split('-')
            
            # Zeller's congruence to find weekday
            y_i = int(y); m_i = int(m); d_i = int(d)
            if m_i < 3:
                m_i += 12; y_i -= 1
            k = y_i % 100; j = y_i // 100
            h = (d_i + 13*(m_i+1)//5 + k + k//4 + j//4 + 5*j) % 7
            dn = ["Sat","Sun","Mon","Tue","Wed","Thu","Fri"]
            
            mn = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            ts = t_part[:5] # HH:MM
            ds = "{} {} {} {}".format(dn[h], d, mn[int(m)-1], y)
            return ts, ds
    except Exception as e:
        print("[TS] Err:", e)
        
    return "--:--", ""

# --- Touch ---
_last_touch=0  # debounce — ignore taps within 400ms of last one

def btn_b_held():
    """True while the Core2's middle capacitive button (BtnB) is held down.

    UIFlow 1.0 on Core2 exposes the button as a software shim (`btnB`) on most
    firmware builds, but on some builds it's missing — in which case the
    capacitive zone is reachable directly through the touch panel at y > 240
    (below the LCD), middle third of x.
    """
    try: return bool(btnB.isPressed())
    except: pass
    try:
        if not touch.status(): return False
        p = touch.read()
        if not p: return False
        x, y = p[0], p[1]
        return y > 240 and 110 <= x <= 220
    except: pass
    return False

def chk_touch():
    """Detect taps. Bottom strip → nav action string ('left'/'right'); the
    middle zone is a dead zone (returns None) since voice queries are now
    triggered by the physical BtnB. Body taps → ('tap', x, y) tuple so the
    active screen can route them.
    """
    global _last_touch
    try:
        if not touch.status(): return None
        p=touch.read()
        if not p: return None
        # touch.read() can return [x,y] or [x,y,pressure] depending on UIFlow ver
        x,y=p[0],p[1]
        # Debounce: 400ms between taps to prevent double-fires from finger drag
        tnow=time.ticks_ms()
        if time.ticks_diff(tnow,_last_touch)<400: return None
        _last_touch=tnow
        print("[TOUCH] x={} y={}".format(x,y))
        if y>160:
            if x<110: return "left"
            if x>210: return "right"
            return None  # middle of nav strip — no action
        return ("tap",x,y)
    except Exception as e:
        print("[TOUCH] err:",e)
    return None

def settings_tap_to_row(x,y):
    """Map a body-tap (x,y) on the settings screen to a row index, or -1."""
    if y < _SET_ROW_Y0 or y > _SET_ROW_Y0 + _SET_N_ROWS * _SET_ROW_H: return -1
    if x < 10 or x > W - 10: return -1
    idx = (y - _SET_ROW_Y0) // _SET_ROW_H
    if idx < 0 or idx >= _SET_N_ROWS: return -1
    return idx

# --- WiFi status display ---
_WIFI_LINES=[]
def _wifi_status(msg):
    global _WIFI_LINES
    print("[WIFI]",msg)
    _WIFI_LINES.append(msg[:38])
    if len(_WIFI_LINES)>8: _WIFI_LINES=_WIFI_LINES[-8:]
    lcd.clear(BG)
    lcd.rect(0,0,W,22,PRI,PRI); lcd.font(lcd.FONT_Default)
    lcd.print("WiFi Setup",W//2-30,4,WHT)
    y=30
    for ln in _WIFI_LINES:
        lcd.print(ln,8,y,WHT); y+=18

# --- Main Loop ---
def loop():
    # Must be declared before any read of VOL/BRIGHT in this function
    # (we both read them in playback gating and mutate them in the cur==7 tap handler).
    global VOL, BRIGHT
    print("[MAIN] Starting Weather Station...")
    try:
        from wifi_manager import connect_wifi
        connect_wifi(status_cb=_wifi_status)
    except Exception as e:
        print("[WIFI] Manager error:",e)
    sync_ntp()
    init_location()  # IP geolocation or load saved manual override
    load_device_settings(); apply_device_settings()
    # resolve_api() is NOT called here — it runs lazily on first API call so
    # the screen draws and buttons are live before any network probe happens.
    cur=0; sd={"t":22.1,"h":46.5,"tv":45,"co":420,"mo":False,"iw":0.0}
    # Seed sd from BigQuery so a freshly-powered-on device shows the last
    # known reading immediately, not the hardcoded defaults above.
    try:
        last=get_latest_bq()
        if last:
            if last.get("temperature") is not None: sd["t"]=last["temperature"]
            if last.get("humidity")    is not None: sd["h"]=last["humidity"]
            if last.get("tvoc")        is not None: sd["tv"]=last["tvoc"]
            if last.get("eco2")        is not None: sd["co"]=last["eco2"]
            print("[BOOT] Seeded from BQ: T={} H={} TVOC={} eCO2={}".format(
                sd["t"],sd["h"],sd["tv"],sd["co"]))
    except Exception as e: print("[BOOT] BQ seed err:",e)
    wx={}; ofc=[]; al=[]; daily=[]; dirty=True; full_draw=True
    # Stagger the first fires so touch becomes responsive before slow network
    # calls run. Sensors (cheap I2C/GPIO) fire immediately; weather/forecast are
    # offset so they fire ~10-15s after boot, by which time the user can already
    # tap buttons. boot_t is captured after sync_ntp() so it reflects real time.
    boot_t = time.time()
    lt_s   = boot_t - SENS_INT + 8      # SHT30: fires 8s into loop (gives touch time to respond)
    lt_sgp = boot_t - SGP_INT           # SGP30: fires on iter 1
    lt_pir = boot_t - PIR_INT           # PIR:   fires on iter 1
    lt_w   = boot_t - WX_INT + 10       # weather fetch ~10s into the loop
    lt_of  = boot_t - FC_INT  + 15      # outdoor forecast fetch ~15s into the loop
    lt_h   = boot_t - HIST_INT + 18     # daily stats fetch ~18s into the loop
    # First motion alert can fire ANN_BOOT_DELAY (120s) after boot. After that,
    # subsequent alerts respect the ANN_CD (10 min) cooldown.
    lt_a   = boot_t - ANN_CD + ANN_BOOT_DELAY
    lt_d   = 0
    lt_sgp_d = 0  # last time Air Quality screen was refreshed with live CO2
    ts,ds=get_ts()
    dd={"ts":ts,"ds":ds,"t":sd["t"],"h":sd["h"],"tv":sd["tv"],"co":sd["co"],"iw":sd.get("iw",0.0),
        "ot":None,"oh":None,"ow":None,"oc":"clear","ofc":[],"al":[],"daily":[]}
    SCREENS[cur](dd, f=True)
    while True:
        try:
            now=time.time(); ts,ds=get_ts()
            # Poll touch at very top — catches taps during the idle 60s SCR_INT window.
            ta=chk_touch()
            # SHT30: temp/humidity every 60s
            if now-lt_s>=SENS_INT:
                t,h=read_sht30()
                if t is not None: sd["t"]=t; sd["h"]=h
                push_data(sd); lt_s=now; dirty=True  # push_data is a blocking POST
                _t=chk_touch()
                if _t: ta=_t  # catch taps that arrived during the network call
                print("[MAIN] T={} H={}".format(sd["t"],sd["h"]))
            # SGP30: read every 1s (datasheet requirement for baseline algorithm).
            # Only trigger a display refresh when the Air Quality screen is active,
            # and at most every 5s to avoid constant redraws blocking touch.
            if now-lt_sgp>=SGP_INT:
                co,tv=read_sgp30()
                if co is not None: sd["co"]=co; sd["tv"]=tv
                lt_sgp=now
                if cur==1 and now-lt_sgp_d>=5:
                    dirty=True; lt_sgp_d=now
            # PIR: motion every 2s. Don't mark dirty on state change — avoids
            # constant redraws that would block touch input.
            if now-lt_pir>=PIR_INT:
                sd["mo"]=read_pir()
                lt_pir=now
            if now-lt_w>=WX_INT:
                nw=get_weather()  # blocking GET
                if nw: wx=nw; print("[MAIN] Wx: {}C {}".format(wx.get("ot"),wx.get("oc")))
                lt_w=now; dirty=True
                _t=chk_touch()
                if _t: ta=_t
            if now-lt_of>=FC_INT:
                nof=get_outdoor_forecast()  # blocking GET (OWM 5-day)
                if nof: ofc=nof; print("[MAIN] OFc: {} days".format(len(ofc)))
                lt_of=now; dirty=True
                _t=chk_touch()
                if _t: ta=_t
            if now-lt_h>=HIST_INT:
                nh=get_daily_stats()  # blocking GET (BQ aggregation)
                if nh: daily=nh; print("[MAIN] Hist: {} days".format(len(daily)))
                lt_h=now; dirty=True
                _t=chk_touch()
                if _t: ta=_t
            # Only redraw if data changed or every SCR_INT seconds
            if dirty or now-lt_d>=SCR_INT:
                al=gen_alerts(sd,wx)
                _update_led(al)
                dd={"ts":ts,"ds":ds,"t":sd["t"],"h":sd["h"],"tv":sd["tv"],"co":sd["co"],"iw":sd.get("iw",0.0),
                    "ot":wx.get("ot"),"oh":wx.get("oh"),"ow":wx.get("ow"),
                    "oc":wx.get("oc","clear"),"ofc":ofc,"al":al,"daily":daily}
                SCREENS[cur](dd, f=full_draw)
                dirty=False; full_draw=False; lt_d=now
            if sd.get("mo") and now-lt_a>=ANN_CD:
                lt_a=now  # set immediately so a second motion pulse doesn't re-trigger
                # Run the ENTIRE pipeline (fetch + play) in a background thread.
                # Previously the fetch (Gemini + TTS) ran in the main loop and
                # froze touch for 3-7s. Now the main loop keeps running while
                # the backend works.
                def _bg_announce():
                    try:
                        aud = voice_announce()
                        if aud and VOL > 0:
                            with open('/flash/announce.wav','wb') as _f: _f.write(aud)
                            try: speaker.playWAV('/flash/announce.wav',16000)
                            except: speaker.playWAV('/flash/announce.wav')
                    except Exception as e: print("[ANN] BG err:",e)
                try:
                    import _thread
                    _thread.start_new_thread(_bg_announce, ())
                except Exception as te:
                    # _thread unavailable on this firmware — fall back to blocking.
                    print("[ANN] No thread, running blocking:",te)
                    _bg_announce()
            # Apply the touch action collected above
            if ta=="left" and cur>0: cur-=1; dirty=True; full_draw=True
            elif ta=="right" and cur<7: cur+=1; dirty=True; full_draw=True
            elif type(ta) is tuple and ta[0]=="tap" and cur==5:
                # Body tap on the Settings screen — pick a location.
                row=settings_tap_to_row(ta[1],ta[2])
                if row==0:
                    set_auto_location()
                elif row>0:
                    set_manual_city(CITY_PRESETS[row-1])
                if row>=0:
                    # Force weather + forecast to refetch with new coords next loop
                    wx={}; ofc=[]; lt_w=0; lt_of=0
                    dirty=True; full_draw=True
            elif type(ta) is tuple and ta[0]=="tap" and cur==6:
                # Body tap on the WiFi screen — only the "Change WiFi" button reacts.
                tx,ty=ta[1],ta[2]
                if (_WIFI_BTN_X <= tx <= _WIFI_BTN_X+_WIFI_BTN_W and
                    _WIFI_BTN_Y <= ty <= _WIFI_BTN_Y+_WIFI_BTN_H):
                    lcd.rect(20,50,W-40,140,CARD,CARD); lcd.rect(20,50,W-40,140,ACC)
                    lcd.font(lcd.FONT_Default)
                    lcd.print("Starting WiFi setup...",55,90,WHT)
                    lcd.print("Join 'M5Weather-Setup'",45,110,DIM)
                    lcd.print("then open http://192.168.4.1",20,130,DIM)
                    time.sleep(2)
                    try:
                        from wifi_manager import start_captive_portal
                        start_captive_portal(status_cb=_wifi_status)
                    except Exception as e: print("[WIFI] portal err:",e)
                    dirty=True; full_draw=True
            elif type(ta) is tuple and ta[0]=="tap" and cur==7:
                tx,ty=ta[1],ta[2]
                changed=False
                if _DS_BTN_Y_VOL<=ty<=_DS_BTN_Y_VOL+_DS_BTN_H:
                    if _DS_BTN_X_MINUS<=tx<=_DS_BTN_X_MINUS+_DS_BTN_W:
                        VOL=max(0,VOL-1); changed=True
                    elif _DS_BTN_X_PLUS<=tx<=_DS_BTN_X_PLUS+_DS_BTN_W:
                        VOL=min(10,VOL+1); changed=True
                elif _DS_BRI_Y<=ty<=_DS_BRI_Y+_DS_BRI_H:
                    if tx < 110: BRIGHT=1
                    elif tx < 204: BRIGHT=2
                    else: BRIGHT=3
                    changed=True
                if changed:
                    apply_device_settings()
                    save_device_settings()
                    dirty=True; full_draw=True
            # Voice query: triggered by holding the physical middle button (BtnB).
            # Records while held (capped at 8 s), processes on release.
            elif btn_b_held():
                print("[MAIN] BtnB held — recording")
                lcd.rect(40,70,W-80,100,CARD,CARD); lcd.rect(40,70,W-80,100,ACC)
                lcd.circle(W//2,105,15,ACC,ACC); lcd.font(lcd.FONT_Default)
                lcd.print("*",W//2-3,99,WHT); lcd.font(lcd.FONT_DejaVu18)
                wav=rec_wav_while(btn_b_held, max_ms=8000)
                # If max_ms hit while still held, wait for release before
                # processing so the user knows recording has stopped.
                while btn_b_held(): time.sleep_ms(50)
                if wav:
                    ans, tr, aud = voice_query(wav)
                    if ans:
                        # Start audio first — Core2 speaker.playWAV() is DMA-based
                        # and returns immediately, so voice begins while the text
                        # box is still being drawn. Tapping dismisses only the box;
                        # speaker is not stopped so voice continues after close.
                        if aud and VOL > 0:
                            try:
                                # WAV is already at correct volume (backend scaled it).
                                with open('/flash/answer.wav', 'wb') as _f: _f.write(aud)
                                try: speaker.playWAV('/flash/answer.wav', 16000)
                                except: speaker.playWAV('/flash/answer.wav')
                            except Exception as e: print("[SPK] Err:",e)
                        lcd.rect(20,50,W-40,140,CARD,CARD); lcd.rect(20,50,W-40,140,PRI)
                        lcd.font(lcd.FONT_Default); lcd.print("Answer:",35,60,ACC)
                        if tr: lcd.print("Heard:"+tr[:22],35,68,DIM)
                        lcd.print("(tap to skip)",W-90,60,DIM)
                        yp=82; words=ans.split(); ln=""
                        for w2 in words:
                            if len(ln)+len(w2)+1>35:
                                lcd.print(ln,35,yp,WHT); yp+=16; ln=w2
                                if yp>170: lcd.print("...",35,yp,DIM); break
                            else: ln=("{} {}".format(ln,w2)).strip()
                        if ln and yp<=170: lcd.print(ln,35,yp,WHT)
                        # Wait for a tap to dismiss the box. Voice keeps playing.
                        end_t = time.ticks_add(time.ticks_ms(), 15000)
                        while time.ticks_diff(end_t, time.ticks_ms()) > 0:
                            if chk_touch() is not None: break
                            time.sleep_ms(50)
                dirty=True; full_draw=True
            time.sleep(0.02)  # short sleep keeps touch responsive (~20ms)
        except KeyboardInterrupt: break
        except Exception as e: print("[ERR] {}".format(e)); time.sleep(5)

loop()
