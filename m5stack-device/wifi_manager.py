"""WiFi manager with captive portal fallback for first-boot setup.

Behavior:
1. If already connected (UIFlow may have done so), return immediately.
2. Otherwise try stored credentials from /flash/wifi.json.
3. If that fails or no creds stored, start an AP and serve a small HTTP form
   on http://192.168.4.1/. On submit, save creds and reboot.
"""
import network
import socket
import json
import time
import machine

WIFI_FILE = '/flash/wifi.json'
AP_SSID   = 'M5Weather-Setup'
AP_PASS   = '12345678'         # 8+ chars required by WPA2
PORTAL_IP = '192.168.4.1'


def _load_creds():
    try:
        with open(WIFI_FILE, 'r') as f:
            return json.load(f)
    except:
        return None


def _save_creds(ssid, pwd):
    with open(WIFI_FILE, 'w') as f:
        json.dump({'ssid': ssid, 'pwd': pwd}, f)


def _try_connect(ssid, pwd, timeout=15, status_cb=None):
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if sta.isconnected():
        return True
    if status_cb: status_cb("Connecting to {}".format(ssid[:20]))
    try:
        sta.connect(ssid, pwd)
    except Exception as e:
        print('[WIFI] connect err:', e)
        return False
    t0 = time.time()
    while time.time() - t0 < timeout:
        if sta.isconnected():
            ip = sta.ifconfig()[0]
            if status_cb: status_cb("OK: {}".format(ip))
            return True
        time.sleep(0.5)
    return False


_PORTAL_HTML = """<!DOCTYPE html><html><head>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>M5Stack WiFi Setup</title>
<style>body{font-family:sans-serif;background:#1a1a2e;color:#fff;padding:18px;max-width:380px;margin:auto}
input{width:100%;padding:10px;margin:8px 0;background:#16213e;border:1px solid #0f3460;color:#fff;border-radius:4px;box-sizing:border-box;font-size:16px}
button{width:100%;padding:12px;background:#e94560;color:#fff;border:0;border-radius:4px;font-size:16px;margin-top:10px}
h1{color:#e94560;margin-bottom:4px}p{color:#8899aa;margin-top:0}</style></head>
<body><h1>WiFi Setup</h1><p>Connect your weather station to the internet.</p>
<form method=POST action=/save>
<label>Network (SSID):</label><input name=ssid required>
<label>Password:</label><input name=pwd type=password>
<button type=submit>Save & Reboot</button></form></body></html>"""

_DONE_HTML = """<!DOCTYPE html><html><head><title>Saved</title></head>
<body style="font-family:sans-serif;background:#1a1a2e;color:#fff;padding:20px;text-align:center">
<h1 style="color:#00d68f">Saved!</h1>
<p>The device will reboot and try to connect.</p></body></html>"""


def _urldecode(s):
    s = s.replace('+', ' ')
    out = ''; i = 0
    while i < len(s):
        if s[i] == '%' and i + 2 < len(s):
            try:
                out += chr(int(s[i+1:i+3], 16))
                i += 3; continue
            except: pass
        out += s[i]; i += 1
    return out


def _parse_form(body):
    out = {}
    for kv in body.split('&'):
        if '=' in kv:
            k, v = kv.split('=', 1)
            out[k] = _urldecode(v)
    return out


def _start_portal(status_cb=None):
    # Switch off STA, turn on AP
    sta = network.WLAN(network.STA_IF); sta.active(False)
    ap  = network.WLAN(network.AP_IF);  ap.active(True)
    try:
        ap.config(essid=AP_SSID, password=AP_PASS, authmode=network.AUTH_WPA_WPA2_PSK)
    except:
        ap.config(essid=AP_SSID, password=AP_PASS)
    if status_cb:
        status_cb("Setup needed!")
        status_cb("Join WiFi: " + AP_SSID)
        status_cb("Password: " + AP_PASS)
        status_cb("Open: http://" + PORTAL_IP)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 80))
    s.listen(1)
    print('[WIFI] Captive portal listening on', PORTAL_IP)

    while True:
        try:
            conn, addr = s.accept()
            req = conn.recv(2048).decode('utf-8', 'ignore')
            line = req.split('\r\n', 1)[0]
            parts = line.split(' ')
            method = parts[0] if parts else ''
            path   = parts[1] if len(parts) > 1 else ''

            if method == 'POST' and path == '/save':
                body = req.split('\r\n\r\n', 1)[1] if '\r\n\r\n' in req else ''
                form = _parse_form(body)
                ssid = form.get('ssid', '').strip()
                pwd  = form.get('pwd', '')
                if ssid:
                    _save_creds(ssid, pwd)
                    conn.send(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n' + _DONE_HTML.encode())
                    conn.close(); s.close()
                    if status_cb: status_cb("Saved. Rebooting...")
                    time.sleep(2)
                    machine.reset()
                else:
                    conn.send(b'HTTP/1.1 400 Bad Request\r\n\r\nMissing SSID')
                    conn.close()
            else:
                conn.send(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n' + _PORTAL_HTML.encode())
                conn.close()
        except Exception as e:
            print('[WIFI] Portal err:', e)


def connect_wifi(status_cb=None):
    """Connect to WiFi. Blocks until connected or until portal reboots the device."""
    sta = network.WLAN(network.STA_IF)
    sta.active(True)

    # UIFlow may have already connected — short-circuit if so
    if sta.isconnected():
        if status_cb: status_cb("WiFi: " + sta.ifconfig()[0])
        return True

    creds = _load_creds()
    if creds and creds.get('ssid'):
        if _try_connect(creds['ssid'], creds.get('pwd', ''), status_cb=status_cb):
            return True
        if status_cb: status_cb("Stored creds failed")

    _start_portal(status_cb=status_cb)
    return False  # portal reboots the device on submit


def start_captive_portal(status_cb=None):
    """Force the captive portal regardless of stored creds."""
    _start_portal(status_cb=status_cb)
